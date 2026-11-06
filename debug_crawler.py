import sqlite3
import httpx
import re
from datetime import datetime

DB_PATH = r"E:\vrcatalogue\data\vrcatalogue.sqlite"

print("==================================================")
print("🔍 1. 시스템 시계 및 DB 최신 날짜 확인")
print("==================================================")
now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
print(f"👉 현재 PC 시계 (datetime.now()): {now_str}")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("SELECT MAX(published_at), MIN(published_at), COUNT(*) FROM items;")
max_date, min_date, total_items = cursor.fetchone()
print(f"👉 DB 내 전체 아이템 수: {total_items:,}개")
print(f"👉 DB 내 가장 최신 날짜: {max_date}")
print(f"👉 DB 내 가장 오래된 날짜: {min_date}")

# 최근 등록된 5개 아이템 조회
cursor.execute("SELECT item_id, shop_name, published_at FROM items ORDER BY published_at DESC LIMIT 5;")
print("\n👉 DB 최신순 상위 5개 아이템:")
for r in cursor.fetchall():
    print(f"   - #{r[0]} | 날짜: {r[2]} | 샵: {r[1]}")

print("\n==================================================")
print("🔍 2. BOOTH 실제 웹사이트 최신 피드 탐색 테스트")
print("==================================================")
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "ja,ko;q=0.9,en;q=0.8"
}

url = "https://booth.pm/ja/items?tags%5B%5D=VRChat&sort=new&page=1"
print(f"요청 URL: {url}")

with httpx.Client(timeout=10.0, follow_redirects=True) as client:
    try:
        resp = client.get(url, headers=headers)
        print(f"👉 HTTP 상태 코드: {resp.status_code}")
        print(f"👉 최종 응답 URL: {resp.url}")
        
        # 아이템 ID 정규식 추출
        ids = list(dict.fromkeys(re.findall(r'/items/(\d+)', resp.text)))
        print(f"👉 페이지 1에서 추출된 총 아이템 ID 수: {len(ids)}개")
        print(f"👉 추출된 상위 5개 ID: {ids[:5]}")

        # DB와 대조
        placeholders = ",".join(["?"] * len(ids))
        cursor.execute(f"SELECT item_id FROM items WHERE item_id IN ({placeholders})", [int(x) for x in ids])
        found_in_db = set(r[0] for r in cursor.fetchall())
        new_ones = [int(x) for x in ids if int(x) not in found_in_db]

        print(f"\n👉 이 중 이미 DB에 있는 ID: {len(found_in_db)}개")
        print(f"👉 DB에 없는 진짜 '신규' ID: {len(new_ones)}개 -> {new_ones[:5]}")

    except Exception as e:
        print(f"❌ 요청 중 에러 발생: {e}")

conn.close()
print("==================================================")