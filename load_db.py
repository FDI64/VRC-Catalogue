import sqlite3
from huggingface_hub import hf_hub_download

REPO_ID = "vrcatalogue/vrcatalogue-open-data"
FILENAME = "vrcatalogue.sqlite"

print("1. Hugging Face에서 SQLite 파일 다운로드 중 (약 수십 MB)...")
db_path = hf_hub_download(
    repo_id=REPO_ID,
    filename=FILENAME,
    repo_type="dataset",
    local_dir="./data"
)
print(f"다운로드 완료: {db_path}")

print("\n2. SQLite 데이터베이스 연결 및 확인...")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 테이블 목록 확인
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [row[0] for row in cursor.fetchall()]
print(f"포함된 테이블: {tables}")

# 기본 통계 확인
cursor.execute("SELECT count(*) FROM items;")
print(f"총 등록 아이템 수: {cursor.fetchone()[0]:,}개")

cursor.execute("SELECT count(*) FROM avatars;")
print(f"등록된 베이스 아바타 수: {cursor.fetchone()[0]:,}개")

conn.close()