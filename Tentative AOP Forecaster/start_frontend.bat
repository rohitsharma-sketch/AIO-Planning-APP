@echo off
REM Fixed 2026-09-23: same stale-path issue as start_backend.bat - was
REM pointing at a legacy pre-fix copy of this folder. Note: this runs the
REM dev server (npm run dev), which is fine for local iteration but is NOT
REM what the deployed app serves - the real app.py mounts frontend/dist/,
REM so any source change here still needs `npm run build` + committing
REM dist/ before it's visible at localhost:8010 or :8000.
set PATH=%LOCALAPPDATA%\node\node-v20.19.2-win-x64;%PATH%
cd /d "%~dp0frontend"
npm run dev
pause
