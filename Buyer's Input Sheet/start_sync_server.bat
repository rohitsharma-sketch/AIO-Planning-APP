@echo off
title CityKart OTB Sync Server
echo Installing dependencies (first run only)...
pip install flask flask-cors pandas pyarrow openpyxl --quiet
echo.
echo Starting sync server on http://localhost:5050
echo Leave this window open while using the OTB app.
echo.
python "%~dp0sync_server.py"
pause
