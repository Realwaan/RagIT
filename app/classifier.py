"""Compatibility alias for app.auditing.classifier; preserves monkeypatch identity."""
import importlib
import sys

_real_module = importlib.import_module("app.auditing.classifier")
sys.modules[__name__] = _real_module
