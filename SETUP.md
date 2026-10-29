# RagIT local setup

Install Python 3.13, Node.js, and Git. From the repository root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt -c constraints-windows-py313.txt
npm ci
```

For a new installation, copy `.env.example` to `.env` only if `.env` does not already exist. Configure your inference provider and Clerk application using your own credentials. Never commit or share credentials.

```powershell
npm run build
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://localhost:8000 and sign in. Initial model downloads require internet access. Subsequent document processing uses the local model cache.

Run local verification before releasing:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check.ps1 -Browser
```

See README.md for authentication and deployment constraints. Local development settings are not a production deployment configuration.
