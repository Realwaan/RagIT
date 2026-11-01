# Cloudflare Tunnel Launcher for RagIT
param(
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  🛡️ RagIT — Cloudflare Zero Trust Secure Tunnel" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

# Ensure cloudflared is located
$cloudflaredCmd = "cloudflared"
if (Test-Path "C:\Program Files (x86)\cloudflared\cloudflared.exe") {
    $cloudflaredCmd = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
} elseif (Test-Path "C:\Program Files\cloudflared\cloudflared.exe") {
    $cloudflaredCmd = "C:\Program Files\cloudflared\cloudflared.exe"
} elseif (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Error "cloudflared is not installed or not in PATH."
    exit 1
}

# Check if local server is listening on port
$tcpConnection = Test-NetConnection -ComputerName 127.0.0.1 -Port $Port -WarningAction SilentlyContinue
if (-not $tcpConnection.TcpTestSucceeded) {
    Write-Host "[!] RagIT server is not currently running on http://127.0.0.1:$Port" -ForegroundColor Yellow
    Write-Host "    Make sure to start RagIT in another terminal using:" -ForegroundColor Yellow
    Write-Host "    .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port $Port" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host "[✓] RagIT server detected running on http://127.0.0.1:$Port" -ForegroundColor Green
}

Write-Host "Starting Cloudflare Quick Tunnel to http://127.0.0.1:$Port..." -ForegroundColor Cyan
Write-Host "Look for the *.trycloudflare.com link below:" -ForegroundColor Yellow
Write-Host ""

& $cloudflaredCmd tunnel --url "http://127.0.0.1:$Port"
