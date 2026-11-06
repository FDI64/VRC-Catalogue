import sqlite3
import requests
from bs4 import BeautifulSoup
import time

DB_PATH = r"E:\vrcatalogue\data\vrcatalogue.sqlite"

# 1. BOOTH 메타데이터 크롤러 함수
def fetch_booth_item(item_id: int):
    url = f"https://booth.pm/ja/items/{item_id}"
    
    # 봇 차단을 방지하기 위한 일반 브라우저 User-Agent
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,ko;q=0.9,en;q=0.8"
    }

    try:
        response = requests.get(url, headers=headers, timeout=5)
        
        # 비공개나 삭제된 아이템 처리
        if response.status_code == 404:
            return {"status": "deleted_or_private", "item_id": item_id}
        elif response.status_code != 200:
            return {"status": f"error_{response.status_code}", "item_id": item_id}

        soup = BeautifulSoup(response.text, "html.parser")

        # OpenGraph 메타태그에서 핵심 정보 추출
        title_meta = soup.find("meta", property="og:title")
        image_meta = soup.find("meta", property="og:image")
        desc_meta = soup.find("meta", property="og:description")

        return {
            "status": "success",
            "item_id": item_id,
            "url": url,
            "title": title_meta["content"] if title_meta else "No Title",
            "thumbnail_url": image_meta["content"] if image_meta else None,
            "description": desc_meta["content"] if desc_meta else ""
        }

    except Exception as e:
        return {"status": f"exception: {str(e)}", "item_id": item_id}


# 2. DB에서 테스트할 인기 아이템 몇 개 가져오기
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# 좋아요가 많은 아이템 3개 조회
query = """
SELECT item_id, likes, price_jpy, quest_compatible, uses_modular_avatar 
FROM items 
WHERE is_adult = 0 
ORDER BY likes DESC 
LIMIT 3;
"""
cursor.execute(query)
sample_items = cursor.fetchall()
conn.close()

print(f"--- DB에서 조회된 상위 3개 아이템 테스트 ---")
for row in sample_items:
    item_id, likes, price, quest, ma = row
    print(f"\n[Item ID: {item_id}] (좋아요: {likes:,}개 | 가격: {price}엔 | MA지원: {bool(ma)})")
    
    # BOOTH에서 실시간 페치
    result = fetch_booth_item(item_id)
    
    if result["status"] == "success":
        print(f"👉 제목: {result['title']}")
        print(f"👉 썸네일: {result['thumbnail_url']}")
        print(f"👉 링크: {result['url']}")
    else:
        print(f"❌ 페치 실패 / 상태: {result['status']}")

    time.sleep(1)  # BOOTH 서버 매너 딜레이 (1초)