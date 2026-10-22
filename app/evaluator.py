"""Compatibility alias for app.auditing.evaluator; preserves monkeypatch identity."""
import importlib
import sys

_real_module = importlib.import_module("app.auditing.evaluator")
sys.modules[__name__] = _real_module
