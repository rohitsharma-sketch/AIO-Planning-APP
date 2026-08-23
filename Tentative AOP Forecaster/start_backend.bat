@echo off
cd /d "C:\Users\A9820\Documents\CLaude - New Projects\Tentative AOP Forecaster"
python -m uvicorn app:app --port 8000 --reload
pause
