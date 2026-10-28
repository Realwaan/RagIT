"""Legacy pipeline tests explicitly use local mode; auth tests override it."""
import pytest


@pytest.fixture(autouse=True)
def local_pipeline_mode(monkeypatch):
    monkeypatch.setenv('RAGIT_AUTH_MODE', 'local')
