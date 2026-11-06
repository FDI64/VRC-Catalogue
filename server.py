import asyncio
import hashlib
import json
import os
import re
import secrets
import sqlite3
import unicodedata
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, Query, BackgroundTasks, Request, Response, HTTPException, Depends
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator, MyMemoryTranslator

DB_PATH = r"E:\vrcatalogue\data\vrcatalogue.sqlite"
HTML_PATH = r"E:\vrcatalogue\index.html"
AUTH_FILE_PATH = r"E:\vrcatalogue\auth_config.json"

app = FastAPI(title="VRChat BOOTH Catalogue")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FETCH_SEMAPHORE = asyncio.Semaphore(6)
CRAWL_SEMAPHORE = asyncio.Semaphore(5)

sync_status = {
    "is_running": False,
    "progress_msg": "대기 중",
    "last_synced": None,
    "new_count": 0
}

# 🔐 인증 세션 풀
active_sessions = set()

# -------------------------------------------------------------
# 🛡️ 비밀번호 로컬 파일 암호화 / 검증 헬퍼
# -------------------------------------------------------------
def hash_password(password: str, salt: bytes = None) -> (str, str):
    if salt is None:
        salt = secrets.token_bytes(16)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100_000)
    return salt.hex(), pwd_hash.hex()

def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    salt = bytes.fromhex(salt_hex)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100_000)
    return secrets.compare_digest(pwd_hash.hex(), hash_hex)

def is_auth_configured() -> bool:
    return os.path.exists(AUTH_FILE_PATH)

def check_login(request: Request):
    token = request.cookies.get("catalogue_session")
    if not is_auth_configured():
        return True # 최초 설정 전에는 허용
    if not token or token not in active_sessions:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    return True

# -------------------------------------------------------------
# 🔑 인증 API 엔드포인트
# -------------------------------------------------------------
class PasswordPayload(BaseModel):
    password: str

@app.get("/api/auth/status")
def auth_status(request: Request):
    needs_setup = not is_auth_configured()
    token = request.cookies.get("catalogue_session")
    is_authed = bool(token and token in active_sessions)
    return {"needs_setup": needs_setup, "is_authenticated": is_authed}

@app.post("/api/auth/setup")
def setup_password(payload: PasswordPayload, response: Response):
    if is_auth_configured():
        raise HTTPException(status_code=400, detail="이미 비밀번호가 설정되어 있습니다.")
    
    if len(payload.password.strip()) < 4:
        raise HTTPException(status_code=400, detail="비밀번호는 최소 4자리 이상이어야 합니다.")

    salt_hex, hash_hex = hash_password(payload.password.strip())
    config_data = {
        "salt": salt_hex,
        "hash": hash_hex,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(AUTH_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)

    # 설정 완료 후 즉시 세션 발급
    new_token = secrets.token_hex(32)
    active_sessions.add(new_token)
    response.set_cookie(key="catalogue_session", value=new_token, httponly=True, samesite="lax", max_age=86400*30)
    print("🔒 [보안] 새 비밀번호가 암호화되어 로컬 파일(auth_config.json)에 저장되었습니다.")
    return {"status": "success", "message": "비밀번호 설정 완료"}

@app.post("/api/auth/login")
def login(payload: PasswordPayload, response: Response):
    if not is_auth_configured():
        raise HTTPException(status_code=400, detail="먼저 초기 비밀번호 생성을 진행해 주세요.")

    try:
        with open(AUTH_FILE_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        raise HTTPException(status_code=500, detail="비밀번호 파일을 읽을 수 없습니다.")

    if verify_password(payload.password.strip(), config["salt"], config["hash"]):
        new_token = secrets.token_hex(32)
        active_sessions.add(new_token)
        response.set_cookie(key="catalogue_session", value=new_token, httponly=True, samesite="lax", max_age=86400*30)
        return {"status": "success", "message": "인증 성공"}
    else:
        raise HTTPException(status_code=401, detail="비밀번호가 일치하지 않습니다.")

@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("catalogue_session")
    if token in active_sessions:
        active_sessions.remove(token)
    response.delete_cookie(key="catalogue_session")
    return {"status": "success", "message": "로그아웃 완료"}

# -------------------------------------------------------------
# 🌐 카탈로그 백엔드 로직
# -------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def has_japanese(text: str) -> bool:
    return bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', text))

async def translate_batch_safe(texts: List[str]) -> List[Optional[str]]:
    results = []
    for raw_text in texts:
        if not raw_text or not raw_text.strip():
            results.append(None)
            continue

        normalized_text = unicodedata.normalize('NFKC', raw_text).strip()
        if not has_japanese(normalized_text):
            results.append(normalized_text)
            continue

        translated = None
        try:
            translated = await asyncio.to_thread(
                GoogleTranslator(source='ja', target='ko').translate, normalized_text
            )
            print(f"✅ [구글 번역] {normalized_text} ➔ {translated}")
            await asyncio.sleep(0.2)
        except Exception:
            try:
                translated = await asyncio.to_thread(
                    MyMemoryTranslator(source='ja-JP', target='ko-KR').translate, normalized_text
                )
                print(f"🔄 [MyMemory 우회] {normalized_text} ➔ {translated}")
                await asyncio.sleep(0.2)
            except Exception as e2:
                print(f"❌ [번역 최종 실패] '{normalized_text}': {e2}")
                translated = normalized_text

        results.append(translated or normalized_text)
    return results

def clean_item_title(raw_title: str, shop: str) -> str:
    if not raw_title:
        return ""
    ct = raw_title
    if ct.endswith(" - BOOTH"):
        ct = ct[:-8]
    if shop and ct.endswith(f" - {shop}"):
        ct = ct[:-(len(shop) + 3)]
    return ct.strip()

def load_avatar_matchers(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT avatar_id, slug, name_ko, name_ja, name_en FROM avatars")
    avs = cursor.fetchall()
    cursor.execute("SELECT avatar_id, alias FROM avatar_aliases")
    als = cursor.fetchall()
    
    matchers = []
    for a in avs:
        for kw in [a["slug"], a["name_ko"], a["name_ja"], a["name_en"]]:
            if kw and len(kw.strip()) >= 2:
                matchers.append((a["avatar_id"], kw.strip().lower()))
    for al in als:
        if al["alias"] and len(al["alias"].strip()) >= 2:
            matchers.append((al["avatar_id"], al["alias"].strip().lower()))
    return matchers

async def parse_single_new_item(client: httpx.AsyncClient, item_id: int, headers: dict, avatar_matchers: list):
    async with CRAWL_SEMAPHORE:
        item_url = f"https://booth.pm/ja/items/{item_id}"
        try:
            resp = await client.get(item_url, headers=headers)
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, "html.parser")
            title_meta = soup.find("meta", property="og:title")
            image_meta = soup.find("meta", property="og:image")
            desc_meta = soup.find("meta", property="og:description")
            
            raw_title = title_meta["content"] if title_meta else f"Item {item_id}"
            thumb_url = image_meta["content"] if image_meta else None
            desc = desc_meta["content"] if desc_meta else ""

            shop_name = "BOOTH Creator"
            shop_url = f"https://booth.pm/ja/items/{item_id}"
            if " - " in raw_title:
                parts = raw_title.split(" - ")
                if len(parts) >= 2:
                    shop_name = parts[-2]
            
            clean_title = clean_item_title(raw_title, shop_name)

            prices = []
            for vb in soup.select(".variation-item, .js-variation-item, [class*='variation']"):
                m = re.findall(r"[¥￥\\]\s*([\d,]+)", vb.get_text())
                for pr in m:
                    try:
                        prices.append(int(pr.replace(",", "")))
                    except:
                        pass
            
            price_jpy = min(prices) if prices else 0
            has_mult_prices = len(set(prices)) > 1 and max(prices) > min(prices)

            raw_pub_date = None
            m_pub = re.search(r'"published_at"\s*:\s*"([^"]+)"', resp.text)
            if m_pub:
                raw_pub_date = m_pub.group(1)

            if not raw_pub_date:
                meta_pub = soup.find("meta", attrs={"property": ["article:published_time", "product:published_time"]})
                if meta_pub and meta_pub.get("content"):
                    raw_pub_date = meta_pub["content"]

            if raw_pub_date:
                try:
                    dt = datetime.fromisoformat(raw_pub_date.replace("Z", "+00:00"))
                    published_at = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    published_at = raw_pub_date[:19] + "Z" if len(raw_pub_date) >= 19 else raw_pub_date
            else:
                published_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

            full_text_lower = (raw_title + " " + desc).lower()
            uses_ma = 'yes' if any(k in full_text_lower for k in ['modular avatar', 'modularavatar', ' ma']) else 'no'
            is_quest = 'yes' if 'quest' in full_text_lower else 'no'
            uses_liltoon = 'yes' if any(k in full_text_lower for k in ['liltoon', '릴툰']) else 'no'
            uses_poiyomi = 'yes' if any(k in full_text_lower for k in ['poiyomi', '포이요미']) else 'no'
            uses_vrcfury = 'yes' if any(k in full_text_lower for k in ['vrcfury', '퓨리']) else 'no'
            is_adult = 1 if 'r-18' in full_text_lower else 0
            content_rating = 'r18' if is_adult else 'all_ages'

            matched_avatar_ids = set()
            for av_id, kw in avatar_matchers:
                if kw in full_text_lower:
                    matched_avatar_ids.add(av_id)

            cat_id = 1
            booth_category = "3D衣装・装飾"
            if any(k in full_text_lower for k in ['ヘア', 'hair', '髪', '헤어']):
                cat_id = 2
                booth_category = "3D髪型"
            elif any(k in full_text_lower for k in ['アクセサリー', 'accessory', 'メガネ', '안경', 'ピアス']):
                cat_id = 3
                booth_category = "3D装飾"
            elif any(k in full_text_lower for k in ['ギミック', 'gimmick', '소품', 'prop', '小物']):
                cat_id = 4
                booth_category = "3D小道具"

            return {
                "item_id": item_id,
                "booth_url": item_url,
                "shop_name": shop_name,
                "shop_url": shop_url,
                "booth_category": booth_category,
                "price_jpy": price_jpy,
                "is_adult": is_adult,
                "published_at": published_at,
                "content_rating": content_rating,
                "uses_ma": uses_ma,
                "is_quest": is_quest,
                "uses_liltoon": uses_liltoon,
                "uses_poiyomi": uses_poiyomi,
                "uses_vrcfury": uses_vrcfury,
                "raw_title": raw_title,
                "clean_title": clean_title,
                "thumb_url": thumb_url,
                "has_mult_prices": has_mult_prices,
                "matched_avatar_ids": list(matched_avatar_ids),
                "cat_id": cat_id
            }
        except Exception as e:
            print(f"❌ #{item_id} 스크래핑 실패: {e}")
            return None

async def crawl_booth_new_assets(max_pages: int = 3):
    global sync_status
    if sync_status["is_running"]:
        return

    sync_status["is_running"] = True
    sync_status["progress_msg"] = f"최신 {max_pages}개 페이지 동시 스캔 중..."
    sync_status["new_count"] = 0

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "ja,ko;q=0.9,en;q=0.8"
    }

    discovered_ids = []
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        async def fetch_feed_page(page: int):
            url = f"https://booth.pm/ja/items?tags%5B%5D=VRChat&sort=new&page={page}"
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    return re.findall(r'/items/(\d+)', resp.text)
            except Exception:
                pass
            return []

        feed_tasks = [fetch_feed_page(p) for p in range(1, max_pages + 1)]
        feed_results = await asyncio.gather(*feed_tasks)
        for page_ids in feed_results:
            for item_id in page_ids:
                val = int(item_id)
                if val not in discovered_ids:
                    discovered_ids.append(val)

        conn = get_db()
        cursor = conn.cursor()
        
        if not discovered_ids:
            sync_status["is_running"] = False
            sync_status["progress_msg"] = "피드에서 아이템을 가져오지 못했습니다."
            conn.close()
            return

        placeholders = ",".join(["?"] * len(discovered_ids))
        cursor.execute(f"SELECT item_id FROM items WHERE item_id IN ({placeholders})", discovered_ids)
        existing_ids = set(r[0] for r in cursor.fetchall())
        new_ids = [i for i in discovered_ids if i not in existing_ids]

        if not new_ids:
            sync_status["is_running"] = False
            sync_status["progress_msg"] = "이미 모든 에셋이 최신 상태입니다 (신작 0개)."
            sync_status["last_synced"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.close()
            return

        avatar_matchers = load_avatar_matchers(conn)
        total_new = len(new_ids)
        completed = 0

        async def wrapped_worker(i_id: int):
            nonlocal completed
            res = await parse_single_new_item(client, i_id, headers, avatar_matchers)
            completed += 1
            sync_status["progress_msg"] = f"신작 수집 중 ({completed}/{total_new})..."
            return res

        workers = [wrapped_worker(i_id) for i_id in new_ids]
        parsed_results = await asyncio.gather(*workers)

        new_added_count = 0
        for item in parsed_results:
            if not item:
                continue

            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO items (
                        item_id, booth_url, shop_name, shop_url, booth_category,
                        price_jpy, likes, is_adult, status, published_at,
                        content_rating, quest_compatible, uses_liltoon, uses_poiyomi,
                        uses_vrcfury, uses_modular_avatar
                    ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, 'ok', ?, ?, ?, ?, ?, ?, ?);
                """, (
                    item["item_id"], item["booth_url"], item["shop_name"], item["shop_url"], item["booth_category"],
                    item["price_jpy"], item["is_adult"], item["published_at"], item["content_rating"],
                    item["is_quest"], item["uses_liltoon"], item["uses_poiyomi"], item["uses_vrcfury"], item["uses_ma"]
                ))

                cursor.execute("""
                    INSERT OR REPLACE INTO item_cache (
                        item_id, title, thumbnail_url, is_available, has_multiple_prices
                    ) VALUES (?, ?, ?, 1, ?);
                """, (item["item_id"], item["raw_title"], item["thumb_url"], 1 if item["has_mult_prices"] else 0))

                for av_id in item["matched_avatar_ids"]:
                    cursor.execute("""
                        INSERT OR IGNORE INTO item_avatar_compatibility (item_id, avatar_id, verified)
                        VALUES (?, ?, 0);
                    """, (item["item_id"], av_id))

                cursor.execute("SELECT subcategory_id FROM subcategories WHERE category_id = ? ORDER BY subcategory_id ASC LIMIT 1", (item["cat_id"],))
                sub_row = cursor.fetchone()
                subcat_id = sub_row[0] if sub_row else 1

                cursor.execute("""
                    INSERT OR REPLACE INTO item_categories (item_id, category_id, subcategory_id, is_primary)
                    VALUES (?, ?, ?, 1);
                """, (item["item_id"], item["cat_id"], subcat_id))

                new_added_count += 1
            except Exception as insert_err:
                print(f"❌ #{item['item_id']} DB 삽입 실패: {insert_err}")

        conn.commit()
        conn.close()

    sync_status["is_running"] = False
    sync_status["new_count"] = new_added_count
    sync_status["progress_msg"] = f"완료 ({new_added_count}개 등록됨)"
    sync_status["last_synced"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"🎉 [고속 수집 완료] 총 {new_added_count}개의 신작 에셋이 DB에 성공적으로 등록되었습니다!\n")

@app.on_event("startup")
def init_cache_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS item_cache (
            item_id INTEGER PRIMARY KEY,
            title TEXT,
            title_ko TEXT,
            thumbnail_url TEXT,
            is_available BOOLEAN DEFAULT 1,
            has_multiple_prices BOOLEAN DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(item_cache);")
    columns = [row[1] for row in cursor.fetchall()]
    
    if "has_multiple_prices" not in columns:
        conn.execute("ALTER TABLE item_cache ADD COLUMN has_multiple_prices BOOLEAN DEFAULT 0;")
    if "title_ko" not in columns:
        conn.execute("ALTER TABLE item_cache ADD COLUMN title_ko TEXT;")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_item_categories_fast ON item_categories (category_id, item_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_item_cat_item ON item_categories (item_id, is_primary);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_compat_fast ON item_avatar_compatibility (avatar_id, item_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_item_tags_fast ON item_tags (tag_id, item_id);")

    conn.execute("""
        INSERT OR IGNORE INTO item_categories (item_id, category_id, subcategory_id, is_primary)
        SELECT i.item_id, 1, 1, 1
        FROM items i
        WHERE NOT EXISTS (SELECT 1 FROM item_categories ic WHERE ic.item_id = i.item_id);
    """)
    conn.commit()
    conn.close()

    # 🚀 시작 시 1회 자동 수집 (비밀번호 설정 여부와 무관하게 백그라운드 구동)
    asyncio.create_task(crawl_booth_new_assets(max_pages=2))

@app.get("/", response_class=HTMLResponse)
def serve_index():
    if os.path.exists(HTML_PATH):
        return FileResponse(HTML_PATH)
    return "<h1>index.html을 찾을 수 없습니다. 경로를 확인하세요.</h1>"

# 🛡️ 아래의 모든 데이터 API는 로그인 검증(check_login)을 거침
@app.get("/api/sync-status", dependencies=[Depends(check_login)])
def get_sync_status():
    return sync_status

@app.post("/api/sync-new-items", dependencies=[Depends(check_login)])
def trigger_sync(background_tasks: BackgroundTasks):
    global sync_status
    if sync_status["is_running"]:
        return {"status": "busy", "message": "이미 동기화 작업이 진행 중입니다."}
    
    background_tasks.add_task(crawl_booth_new_assets, max_pages=3)
    return {"status": "started", "message": "신규 에셋 수집을 시작했습니다."}

@app.get("/api/translate-items", dependencies=[Depends(check_login)])
async def translate_items_on_demand(item_ids: str = Query(...)):
    conn = get_db()
    cursor = conn.cursor()
    ids = [int(x) for x in item_ids.split(",") if x.strip().isdigit()]
    if not ids:
        conn.close()
        return {"translations": {}}

    placeholders = ",".join(["?"] * len(ids))
    query = f"""
        SELECT c.item_id, c.title, c.title_ko, i.shop_name 
        FROM item_cache c
        LEFT JOIN items i ON c.item_id = i.item_id
        WHERE c.item_id IN ({placeholders});
    """
    cursor.execute(query, ids)
    rows = [dict(r) for r in cursor.fetchall()]

    needs_trans = []
    results = {}

    for r in rows:
        if r.get("title_ko"):
            results[r["item_id"]] = r["title_ko"]
        elif r.get("title"):
            c_title = clean_item_title(r["title"], r.get("shop_name") or "")
            needs_trans.append((r["item_id"], c_title))

    if needs_trans:
        titles_to_translate = [x[1] for x in needs_trans]
        translated = await translate_batch_safe(titles_to_translate)
        for (item_id, _), t_ko in zip(needs_trans, translated):
            if t_ko:
                cursor.execute("UPDATE item_cache SET title_ko = ? WHERE item_id = ?", (t_ko, item_id))
                results[item_id] = t_ko
        conn.commit()

    conn.close()
    return {"translations": results}

async def fetch_booth_item(client: httpx.AsyncClient, item_id: int, shop_name: str = ""):
    async with FETCH_SEMAPHORE:
        url = f"https://booth.pm/ja/items/{item_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "ja,ko;q=0.9,en;q=0.8"
        }

        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 404:
                return {
                    "item_id": item_id, 
                    "title": "비공개/삭제된 아이템", 
                    "clean_title": "비공개/삭제된 아이템", 
                    "thumbnail_url": None, 
                    "is_available": False, 
                    "has_multiple_prices": False
                }
            elif resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, "html.parser")
            title_meta = soup.find("meta", property="og:title")
            image_meta = soup.find("meta", property="og:image")
            raw_title = title_meta["content"] if title_meta else "No Title"
            clean_title = clean_item_title(raw_title, shop_name)

            detected_prices = set()
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        offers = data.get("offers")
                        if isinstance(offers, list):
                            for off in offers:
                                if "price" in off:
                                    detected_prices.add(int(float(off["price"])))
                        elif isinstance(offers, dict):
                            if "lowPrice" in offers and "highPrice" in offers:
                                detected_prices.add(int(float(offers["lowPrice"])))
                                detected_prices.add(int(float(offers["highPrice"])))
                            elif "price" in offers:
                                detected_prices.add(int(float(offers["price"])))
                except Exception:
                    pass

            for el in soup.find_all(attrs={"data-price": True}):
                try:
                    detected_prices.add(int(el["data-price"]))
                except (ValueError, TypeError):
                    pass

            for vb in soup.select(".variation-item, .js-variation-item, [class*='variation']"):
                matches = re.findall(r"[¥￥\\]\s*([\d,]+)", vb.get_text())
                for m in matches:
                    try:
                        p = int(m.replace(",", ""))
                        if 0 <= p < 10000000:
                            detected_prices.add(p)
                    except ValueError:
                        pass

            has_multiple_prices = len(detected_prices) > 1 and max(detected_prices) > min(detected_prices)

            return {
                "item_id": item_id, 
                "title": raw_title, 
                "clean_title": clean_title, 
                "thumbnail_url": image_meta["content"] if image_meta else None, 
                "is_available": True, 
                "has_multiple_prices": has_multiple_prices
            }
        except Exception:
            return None

@app.get("/api/avatars", dependencies=[Depends(check_login)])
def get_avatars(search: Optional[str] = None):
    conn = get_db()
    cursor = conn.cursor()
    if search:
        query = """
            SELECT avatar_id, slug, name_ko, name_ja, name_en, compatible_item_count 
            FROM avatars 
            WHERE name_ko LIKE ? OR name_ja LIKE ? OR name_en LIKE ? OR slug LIKE ?
            ORDER BY compatible_item_count DESC 
            LIMIT 30;
        """
        p = f"%{search}%"
        cursor.execute(query, (p, p, p, p))
    else:
        query = """
            SELECT avatar_id, slug, name_ko, name_ja, name_en, compatible_item_count 
            FROM avatars 
            ORDER BY compatible_item_count DESC 
            LIMIT 50;
        """
        cursor.execute(query)

    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

@app.get("/api/categories", dependencies=[Depends(check_login)])
def get_categories():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT category_id, slug, name_ko, name_ja, name_en 
        FROM categories 
        ORDER BY category_id ASC;
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

@app.get("/api/tags", dependencies=[Depends(check_login)])
def search_tags(q: str = Query(..., min_length=1)):
    conn = get_db()
    cursor = conn.cursor()
    kw = q.strip()
    pattern = f"%{kw}%"
    
    query = """
        SELECT t.tag_id, t.name, t.unified_tag_id,
               ut.name_ko, ut.name_ja, ut.name_en
        FROM tags t
        LEFT JOIN unified_tags ut ON t.unified_tag_id = ut.unified_tag_id
        WHERE t.name LIKE :p 
           OR ut.name_ko LIKE :p 
           OR ut.name_ja LIKE :p 
           OR ut.name_en LIKE :p
        ORDER BY 
            CASE 
                WHEN t.name = :exact OR ut.name_ko = :exact THEN 1
                WHEN t.name LIKE :starts OR ut.name_ko LIKE :starts THEN 2
                ELSE 3
            END,
            LENGTH(t.name) ASC
        LIMIT 15;
    """
    cursor.execute(query, {
        "p": pattern,
        "exact": kw,
        "starts": f"{kw}%"
    })
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

@app.get("/api/items", dependencies=[Depends(check_login)])
async def get_items(
    avatar_id: Optional[int] = Query(None),
    category_id: Optional[int] = Query(None),
    ma_only: bool = Query(False),
    sort_by: str = Query("likes", regex="^(likes|trending|newest|price_asc|price_desc)$"),
    search_type: Optional[str] = Query("shop"),
    keyword: Optional[str] = Query(None),
    include_tags: Optional[str] = Query(None),
    exclude_tags: Optional[str] = Query(None),
    translate: bool = Query(False),
    limit: int = Query(12, ge=1, le=50),
    offset: int = Query(0, ge=0)
):
    conn = get_db()
    cursor = conn.cursor()

    conditions = ["i.status = 'ok'"]
    params = {"limit": limit, "offset": offset}
    joins = []

    if avatar_id:
        joins.append("JOIN item_avatar_compatibility compat ON i.item_id = compat.item_id")
        conditions.append("compat.avatar_id = :avatar_id")
        params["avatar_id"] = avatar_id

    if category_id:
        joins.append("""
            JOIN (
                SELECT DISTINCT item_id 
                FROM item_categories 
                WHERE category_id = :category_id
            ) ic_filter ON i.item_id = ic_filter.item_id
        """)
        params["category_id"] = category_id

    if ma_only:
        conditions.append("i.uses_modular_avatar = 'yes'")

    if keyword and keyword.strip():
        kw_clean = keyword.strip()
        params["kw"] = f"%{kw_clean}%"
        if search_type == "title":
            conditions.append("(c.title LIKE :kw OR c.title_ko LIKE :kw)")
        else:
            conditions.append("i.shop_name LIKE :kw")

    if include_tags:
        inc_ids = [int(t) for t in include_tags.split(",") if t.strip().isdigit()]
        for idx, tag_id in enumerate(inc_ids):
            joins.append(f"""
                JOIN item_tags it_inc_{idx} 
                ON i.item_id = it_inc_{idx}.item_id 
                AND it_inc_{idx}.tag_id = :inc_tag_{idx}
            """)
            params[f"inc_tag_{idx}"] = tag_id

    if exclude_tags:
        exc_ids = [int(t) for t in exclude_tags.split(",") if t.strip().isdigit()]
        if exc_ids:
            exc_placeholders = ", ".join([f":exc_tag_{idx}" for idx in range(len(exc_ids))])
            conditions.append(f"""
                NOT EXISTS (
                    SELECT 1 FROM item_tags it_exc 
                    WHERE it_exc.item_id = i.item_id 
                      AND it_exc.tag_id IN ({exc_placeholders})
                )
            """)
            for idx, tag_id in enumerate(exc_ids):
                params[f"exc_tag_{idx}"] = tag_id

    if sort_by == "trending":
        order_clause = """
            ORDER BY (
                (CAST(i.likes AS REAL) + 10.0) / 
                (MAX(1.0, JULIANDAY('2026-11-02') - JULIANDAY(COALESCE(i.published_at, '2020-01-01')) + 14.0))
            ) DESC
        """
    elif sort_by == "newest":
        order_clause = "ORDER BY i.published_at DESC"
    elif sort_by == "price_asc":
        order_clause = "ORDER BY i.price_jpy ASC, i.likes DESC"
    elif sort_by == "price_desc":
        order_clause = "ORDER BY i.price_jpy DESC, i.likes DESC"
    else:
        order_clause = "ORDER BY i.likes DESC"

    join_clause = " ".join(joins)
    where_clause = "WHERE " + " AND ".join(conditions)

    query = f"""
        SELECT i.item_id, i.shop_name, i.shop_url, i.likes, i.price_jpy, i.published_at,
               i.uses_modular_avatar, i.quest_compatible,
               c.title, c.title_ko, c.thumbnail_url, c.is_available,
               COALESCE(c.has_multiple_prices, 0) as has_multiple_prices,
               COALESCE(cat.name_ko, cat.name_ja, cat.name_en) as category_name,
               COALESCE(subcat.name_ko, subcat.name_ja, subcat.name_en) as subcategory_name
        FROM items i
        {join_clause}
        LEFT JOIN item_cache c ON i.item_id = c.item_id
        LEFT JOIN item_categories ic ON i.item_id = ic.item_id AND ic.is_primary = 1
        LEFT JOIN categories cat ON ic.category_id = cat.category_id
        LEFT JOIN subcategories subcat ON ic.subcategory_id = subcat.subcategory_id
        {where_clause}
        {order_clause}
        LIMIT :limit OFFSET :offset;
    """

    cursor.execute(query, params)
    items = [dict(row) for row in cursor.fetchall()]

    uncached_items = [it for it in items if it["title"] is None]
    if uncached_items:
        async with httpx.AsyncClient(timeout=6.0) as client:
            tasks = [fetch_booth_item(client, it["item_id"], it.get("shop_name") or "") for it in uncached_items]
            fetched_results = await asyncio.gather(*tasks)

        valid_results = [r for r in fetched_results if r is not None]

        translated_titles = [None] * len(valid_results)
        if translate:
            titles_to_translate = [r["clean_title"] for r in valid_results]
            translated_titles = await translate_batch_safe(titles_to_translate)

        cache_records = []
        for res, t_ko in zip(valid_results, translated_titles):
            res["title_ko"] = t_ko
            cache_records.append((
                res["item_id"], res["title"], res["title_ko"], res["thumbnail_url"], res["is_available"], 1 if res["has_multiple_prices"] else 0
            ))

        if cache_records:
            cursor.executemany("""
                INSERT OR REPLACE INTO item_cache (item_id, title, title_ko, thumbnail_url, is_available, has_multiple_prices)
                VALUES (?, ?, ?, ?, ?, ?);
            """, cache_records)
            conn.commit()

        res_map = {r["item_id"]: r for r in valid_results}
        for it in items:
            if it["item_id"] in res_map:
                it["title"] = res_map[it["item_id"]]["title"]
                it["title_ko"] = res_map[it["item_id"]]["title_ko"]
                it["thumbnail_url"] = res_map[it["item_id"]]["thumbnail_url"]
                it["is_available"] = res_map[it["item_id"]]["is_available"]
                it["has_multiple_prices"] = res_map[it["item_id"]]["has_multiple_prices"]

    if translate:
        needs_translation = [it for it in items if it.get("title") and not it.get("title_ko")]
        if needs_translation:
            clean_titles = [clean_item_title(it.get("title") or "", it.get("shop_name") or "") for it in needs_translation]
            translated_list = await translate_batch_safe(clean_titles)

            for it, t_ko in zip(needs_translation, translated_list):
                if t_ko:
                    cursor.execute("UPDATE item_cache SET title_ko = ? WHERE item_id = ?", (t_ko, item_id))
                    it["title_ko"] = t_ko
            conn.commit()

    for it in items:
        it["clean_title"] = clean_item_title(it.get("title") or "", it.get("shop_name") or "")

    conn.close()
    return {"items": items}