"""Compatibility alias for app.ingestion.ingest; preserves monkeypatch identity."""
import importlib
import sys

_real_module = importlib.import_module("app.ingestion.ingest")
sys.modules[__name__] = _real_module
