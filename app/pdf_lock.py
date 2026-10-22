"""Compatibility alias for app.ingestion.pdf_lock; preserves monkeypatch identity."""
import importlib
import sys

_real_module = importlib.import_module("app.ingestion.pdf_lock")
sys.modules[__name__] = _real_module
