@echo off
echo Starting DreamSpace servers...

:: Kill existing processes on ports 8001 (backend) and 5173 (frontend)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8001 " ^| findstr "LISTENING"') do (
    echo Killing PID %%a on port 8001
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":5173 " ^| findstr "LISTENING"') do (
    echo Killing PID %%a on port 5173
    taskkill /F /PID %%a >nul 2>&1
)

:: Backend on 8001 (matches frontend API_BASE). --reload-exclude keeps the
:: huge ml/ model tree from triggering reload storms that serve stale code.
start "DreamSpace Backend :8001" cmd /k "cd /d "%~dp0backend" && venv\Scripts\python -m uvicorn main:app --reload --reload-exclude \"ml/*\" --port 8001"

timeout /t 2 /nobreak >nul

:: Start frontend in its own persistent window
start "DreamSpace Frontend :5173" cmd /k "cd /d "%~dp0frontend" && npm run dev -- --port 5173"

echo.
echo Servers launched in separate windows (they will stay open).
echo   Backend:   http://localhost:8001
echo   Frontend:  http://localhost:5173
echo.
echo Open http://localhost:5173 in your browser.
