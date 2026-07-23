@echo off
title DreamSpace Frontend — Port 5173
color 0B
echo.
echo  ██████╗ ██████╗ ███████╗ █████╗ ███╗   ███╗███████╗██████╗  █████╗  ██████╗███████╗
echo  ██╔══██╗██╔══██╗██╔════╝██╔══██╗████╗ ████║██╔════╝██╔══██╗██╔══██╗██╔════╝██╔════╝
echo  ██║  ██║██████╔╝█████╗  ███████║██╔████╔██║███████╗██████╔╝███████║██║     █████╗
echo  ██║  ██║██╔══██╗██╔══╝  ██╔══██║██║╚██╔╝██║╚════██║██╔═══╝ ██╔══██║██║     ██╔══╝
echo  ██████╔╝██║  ██║███████╗██║  ██║██║ ╚═╝ ██║███████║██║     ██║  ██║╚██████╗███████╗
echo  ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝╚═╝     ╚═╝  ╚═╝ ╚═════╝╚══════╝
echo.
echo  [FRONTEND]  React + Vite + Three.js
echo  [URL]       http://localhost:5173
echo.
echo  Starting server... (keep this window open)
echo  ─────────────────────────────────────────────────────────
echo.

cd /d "%~dp0frontend"

:: Kill anything already on port 5173
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":5173 " ^| findstr "LISTENING"') do (
    echo Freeing port 5173 ^(PID %%a^)...
    taskkill /F /PID %%a >nul 2>&1
)

:: Start Vite dev server
npm run dev -- --port 5173

echo.
echo  Server stopped. Press any key to close.
pause >nul
