@echo off
title VRC-Catalogue 빌더
chcp 65001 > nul

echo =======================================================
echo   1. 메인 앱(VRC-Catalogue.exe) 빌드 중... (약 1~2분 소요)
echo =======================================================
py -3.10 -m PyInstaller --name "VRC-Catalogue" --onefile --windowed --add-data "index.html;." --add-data "app.js;." --hidden-import uvicorn.logging --hidden-import uvicorn.loops --hidden-import uvicorn.loops.auto --hidden-import uvicorn.protocols --hidden-import uvicorn.protocols.http --hidden-import uvicorn.protocols.http.auto --hidden-import uvicorn.protocols.websockets --hidden-import uvicorn.protocols.websockets.auto --hidden-import uvicorn.lifespan --hidden-import uvicorn.lifespan.on launcher.py

echo.
echo =======================================================
echo   2. DB 다운로더(DB_Downloader.exe) 빌드 중... 
echo =======================================================
:: 다운로더는 진행률 바(Progress bar)를 봐야 하므로 --windowed 옵션을 뺍니다!
py -3.10 -m PyInstaller --name "DB_Downloader" --onefile load_db.py

echo.
echo =======================================================
echo   빌드가 완료되었습니다! 파일들을 바깥으로 꺼냅니다.
echo =======================================================
move /Y dist\VRC-Catalogue.exe .
move /Y dist\DB_Downloader.exe .

:: 찌꺼기 폴더 삭제
rmdir /S /Q build
rmdir /S /Q dist
del /Q VRC-Catalogue.spec
del /Q DB_Downloader.spec

echo.
echo ✨ 모든 작업이 완료되었습니다! 
pause