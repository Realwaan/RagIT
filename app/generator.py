"""Compatibility alias for app.core.generator; preserves monkeypatch identity."""
import importlib
import sys

_real_module = importlib.import_module("app.core.generator")
sys.modules[__name__] = _real_module
