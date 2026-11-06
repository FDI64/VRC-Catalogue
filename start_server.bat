@echo off
title VRChat BOOTH Catalogue Server
chcp 65001 > nul

:: 현재 bat 파일이 위치한 디렉터리로 이동
cd /d "%~dp0"

echo =======================================================
echo   VRChat BOOTH Asset Catalogue Web Server
echo =======================================================
echo.
echo [1/2] 브라우저 창을 엽니다...
start http://127.0.0.1:8000/

echo [2/2] Python 3.10 기반 FastAPI 서버를 구동합니다...
echo.
echo - 접속 주소: http://127.0.0.1:8000/
echo - 서버 종료: 이 창에서 Ctrl + C 를 누르거나 창을 닫으세요.
echo =======================================================
echo.

:: Python 3.10으로 uvicorn 서버 실행
py -3.10 -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload

:: 서버 비정상 종료 시 에러 메시지를 볼 수 있도록 일시정지
if %errorlevel% neq 0 (
    echo.
    echo ❌ 서버 실행 중 에러가 발생했습니다.
    pause
)