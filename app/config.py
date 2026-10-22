"""Compatibility alias for app.core.config; preserves monkeypatch identity."""
import importlib
import sys

_real_module = importlib.import_module("app.core.config")
sys.modules[__name__] = _real_module
