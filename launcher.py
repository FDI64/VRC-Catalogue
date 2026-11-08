import threading
import time
import uvicorn
import webview
from server import app

# 1. FastAPI 서버를 구동하는 헬퍼 함수
def run_server():
    # reload=False로 설정하여 exe 환경에서 충돌 방지
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="critical")

if __name__ == "__main__":
    # 2. 서버를 백그라운드(데몬 스레드)에서 실행
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # 서버가 켜질 때까지 0.5초 대기
    time.sleep(0.5)

    # 3. 브라우저 대신 독립된 데스크톱 앱 창(WebView) 띄우기
    webview.create_window(
        title="VRC-Catalogue", 
        url="http://127.0.0.1:8000/", 
        width=1280, 
        height=850,
        min_size=(1024, 768),
        background_color="#020617" # 다크 모드 로딩 배경색
    )
    
    # 4. 창 실행 (이 창을 닫으면 파이썬 서버도 자동으로 꺼집니다)
    webview.start()