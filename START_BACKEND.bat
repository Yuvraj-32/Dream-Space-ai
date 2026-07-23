@echo off
title DreamSpace Backend — Port 8001
color 0A
echo.
echo  ██████╗ ██████╗ ███████╗ █████╗ ███╗   ███╗███████╗██████╗  █████╗  ██████╗███████╗
echo  ██╔══██╗██╔══██╗██╔════╝██╔══██╗████╗ ████║██╔════╝██╔══██╗██╔══██╗██╔════╝██╔════╝
echo  ██║  ██║██████╔╝█████╗  ███████║██╔████╔██║███████╗██████╔╝███████║██║     █████╗
echo  ██║  ██║██╔══██╗██╔══╝  ██╔══██║██║╚██╔╝██║╚════██║██╔═══╝ ██╔══██║██║     ██╔══╝
echo  ██████╔╝██║  ██║███████╗██║  ██║██║ ╚═╝ ██║███████║██║     ██║  ██║╚██████╗███████╗
echo  ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝╚═╝     ╚═╝  ╚═╝ ╚═════╝╚══════╝
echo.
echo  [BACKEND]  FastAPI + OpenCV Detection Server
echo  [URL]      http://localhost:8001
echo  [DOCS]     http://localhost:8001/docs
echo.
echo  Starting server... (keep this window open)
echo  ─────────────────────────────────────────────────────────
echo.

cd /d "%~dp0backend"

:: Kill anything already on port 8001 (the port the frontend talks to)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8001 " ^| findstr "LISTENING"') do (
    echo Freeing port 8001 ^(PID %%a^)...
    taskkill /F /PID %%a >nul 2>&1
)

:: Start uvicorn on 8001 (matches frontend API_BASE).
:: --reload-exclude keeps the huge ml/ model tree from triggering reload storms.
venv\Scripts\python -m uvicorn main:app --reload --reload-exclude "ml/*" --port 8001

echo.
echo  Server stopped. Press any key to close.
pause >nul
