"""Compatibility alias for app.core.llm; preserves monkeypatch identity."""
import importlib
import sys

_real_module = importlib.import_module("app.core.llm")
sys.modules[__name__] = _real_module
