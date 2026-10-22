"""Compatibility alias for app.storage.retriever; preserves monkeypatch identity."""
import importlib
import sys

_real_module = importlib.import_module("app.storage.retriever")
sys.modules[__name__] = _real_module
