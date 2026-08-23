@echo off
setlocal

set "PROJECT=C:\Users\A9820\Documents\CLaude - New Projects\Tentative AOP Forecaster"
set "UVICORN=C:\Users\A9820\AppData\Local\Python\pythoncore-3.14-64\Scripts\uvicorn.exe"

:: ── Backend ──────────────────────────────────────────────────────────────────
netstat -ano | findstr /C:":8000 " | findstr LISTENING >nul 2>&1
if errorlevel 1 (
    echo Starting AOP Forecaster...
    start "AOP Forecaster" /min cmd /k "cd /d "%PROJECT%" && "%UVICORN%" app:app --port 8000"
    timeout /t 3 /nobreak >nul
) else (
    echo Already running on :8000
)

:: ── Open browser ─────────────────────────────────────────────────────────────
start "" "http://localhost:8000"

endlocal
