"""Compatibility alias for app.auditing.audit_scanner; preserves monkeypatch identity."""
import importlib
import sys

_real_module = importlib.import_module("app.auditing.audit_scanner")
sys.modules[__name__] = _real_module
