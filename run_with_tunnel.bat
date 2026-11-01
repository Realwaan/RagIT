@echo off
title RagIT + Cloudflare Secure Tunnel
echo ========================================================
echo   🛡️ RagIT — Cloudflare Zero Trust Secure Tunnel
echo ========================================================
echo.

cd /d "%~dp0"

REM Activate virtual environment if present
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

REM 1. Start RagIT Uvicorn in background
echo Starting local RagIT server on http://127.0.0.1:8000 ...
start "RagIT Server" /min cmd /c "python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

REM Wait 3 seconds for Uvicorn to initialize
timeout /t 3 /nobreak >nul

REM 2. Start Cloudflare Tunnel
echo.
echo Launching Cloudflare Tunnel...
echo Copy the https://*.trycloudflare.com link below to access your app from anywhere!
echo ========================================================
echo.

set "CLOUDFLARED_BIN=cloudflared"
if exist "C:\Program Files (x86)\cloudflared\cloudflared.exe" set "CLOUDFLARED_BIN=C:\Program Files (x86)\cloudflared\cloudflared.exe"
if exist "C:\Program Files\cloudflared\cloudflared.exe" set "CLOUDFLARED_BIN=C:\Program Files\cloudflared\cloudflared.exe"

"%CLOUDFLARED_BIN%" tunnel --url http://127.0.0.1:8000
pause
