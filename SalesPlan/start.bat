@echo off
title CityKart Sales Plan
setlocal

set "PORT=8002"
set "URL=http://localhost:%PORT%"
set "PY=C:\Users\A9820\AppData\Local\Python\pythoncore-3.14-64\python.exe"

:: Fall back to whatever python is on PATH if the pinned install is missing
if not exist "%PY%" set "PY=python"

:: Kill any stale LISTENING process on the port so restart is always clean
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /r /c:":%PORT% .*LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)

cd /d "%~dp0backend"

echo.
echo  ================================================
echo   CityKart Sales Plan
echo   Starts: API server + MRP file-watcher
echo   URL   : %URL%
echo   Close this window to stop the server.
echo  ================================================
echo.

:: Background helper: wait until the port is actually listening, then open browser.
:: (ping is used as a sleep because "timeout" fails when stdin is redirected.)
start "" /b cmd /c "for /l %%i in (1,1,60) do (netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul && (start "" "%URL%" & exit /b) || ping -n 2 127.0.0.1 >nul)"

"%PY%" -m uvicorn main:app --host 127.0.0.1 --port %PORT%

if errorlevel 1 (
    echo.
    echo  Server exited with an error. Check the messages above.
    pause
)
endlocal
