"""Compatibility alias for app.ingestion.indexing; preserves monkeypatch identity."""
import importlib
import sys

_real_module = importlib.import_module("app.ingestion.indexing")
sys.modules[__name__] = _real_module
