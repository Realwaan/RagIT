"""Compatibility alias for app.storage.embeddings; preserves monkeypatch identity."""
import importlib
import sys

_real_module = importlib.import_module("app.storage.embeddings")
sys.modules[__name__] = _real_module
