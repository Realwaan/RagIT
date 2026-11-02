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

REM Wait until Uvicorn server is fully initialized and ready
echo Waiting for backend server to become ready...
powershell -NoProfile -Command "for ($i = 0; $i -lt 30; $i++) { try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/ready' -UseBasicParsing -TimeoutSec 1; if ($r.StatusCode -eq 200) { exit 0 } } catch { Start-Sleep -Milliseconds 500 } }; exit 1"
if errorlevel 1 (
    echo ERROR: Backend did not become ready. Cloudflare Tunnel will not start.
    echo Check the RagIT Server window for startup errors.
    pause
    exit /b 1
)
echo Server is online!

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
