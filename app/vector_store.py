"""Compatibility alias for app.storage.vector_store; preserves monkeypatch identity."""
import importlib
import sys

_real_module = importlib.import_module("app.storage.vector_store")
sys.modules[__name__] = _real_module
