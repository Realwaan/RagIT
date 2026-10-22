"""Compatibility alias for app.auditing.discrepancy_scanner; preserves monkeypatch identity."""
import importlib
import sys

_real_module = importlib.import_module("app.auditing.discrepancy_scanner")
sys.modules[__name__] = _real_module
