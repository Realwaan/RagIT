@echo off
title RagIT
echo ===================================================
echo   Starting RagIT
echo   Using configured inference provider
echo ===================================================

cd /d "%~dp0"

REM Activate virtual environment if present
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

REM Open browser in 2 seconds
start "" http://localhost:8000

REM Launch Uvicorn
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
