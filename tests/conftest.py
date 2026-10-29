"""Legacy pipeline tests explicitly use local mode; auth tests override it."""
import pytest


@pytest.fixture(autouse=True)
def local_pipeline_mode(monkeypatch, tmp_path):
    monkeypatch.setenv('RAGIT_AUTH_MODE', 'local')
    from app import main
    from app.processing import ProcessingJobs
    monkeypatch.setattr(main, 'PROCESSING_JOBS', ProcessingJobs(tmp_path / 'processing.sqlite3'))
