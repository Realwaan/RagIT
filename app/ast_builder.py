"""Compatibility alias for app.ingestion.ast_builder; preserves monkeypatch identity."""
import importlib
import sys

_real_module = importlib.import_module("app.ingestion.ast_builder")
sys.modules[__name__] = _real_module
