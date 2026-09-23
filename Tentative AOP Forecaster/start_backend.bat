@echo off
REM Fixed 2026-09-23: was pointing at a stale legacy copy of this folder
REM (C:\Users\A9820\Documents\CLaude - New Projects\Tentative AOP Forecaster,
REM predating the DB integration entirely - no db/publish_aop_targets.py, no
REM engine_bases field) that would silently resurrect pre-fix behavior on
REM every use. This IS the canonical repo copy - cd to itself, no traversal needed.
cd /d "%~dp0"
python -m uvicorn app:app --port 8000 --reload
pause
