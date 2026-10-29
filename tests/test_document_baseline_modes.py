"""Benchmark modes keep provider usage and reported tokens explicit."""
import hashlib
import json
import os
from types import SimpleNamespace

import pytest

from app import generator, indexing, main, vision
from scripts import document_baseline as baseline


@pytest.mark.parametrize('live,live_vision,mode,text_enabled,vision_enabled', [
    (False, False, 'offline_extractive', False, False),
    (False, True, 'extractive_with_live_vision', False, True),
    (True, False, 'live', True, True),
])
def test_modes_and_visual_token_accounting(monkeypatch, tmp_path, live, live_vision,
                                         mode, text_enabled, vision_enabled):
    blob = b'synthetic fixture'
    (tmp_path / 'fixture.pdf').write_bytes(blob)
    manifest = {'version': 1, 'scope': 'test', 'documents': [
        {'id': 'fixture', 'path': 'fixture.pdf', 'split': 'development',
         'sha256': hashlib.sha256(blob).hexdigest()}], 'cases': [
        {'id': 'question', 'document': 'fixture', 'category': 'visual',
         'query': 'What color is the shape?', 'expected_answer': 'blue',
         'answerable': True, 'supporting_pages': [2]}]}
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(baseline, 'DATA', tmp_path)
    monkeypatch.setattr(main, 'DOCUMENT_VAULT', {})
    original_vault = main.DOCUMENT_VAULT
    monkeypatch.setenv('RAGIT_AUTH_MODE', 'clerk')
    monkeypatch.setattr(generator, 'has_valid_primary_key', lambda: True)
    monkeypatch.setattr(generator, 'has_valid_fallback_key', lambda: True)
    monkeypatch.setattr(vision, 'configured', lambda: True)
    monkeypatch.setattr(indexing, 'prepare_document', lambda *args: {
        'doc_id': 'fixture', 'retriever': SimpleNamespace(retrieve=lambda *args, **kwargs: [{'page': 2}])})

    class Client:
        def __init__(self, app):
            pass

        def post(self, url, json):
            assert os.environ['RAGIT_AUTH_MODE'] == 'local'
            assert main.DOCUMENT_VAULT is not original_vault
            assert generator.has_valid_primary_key() is text_enabled
            assert generator.has_valid_fallback_key() is text_enabled
            assert vision.configured() is vision_enabled
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
                'answer': 'The shape is blue. [1]', 'status': 'SUCCESS',
                'sources': [{'citation_id': 1, 'page': 2}],
                'token_telemetry': {'total_tokens': 123}})

    monkeypatch.setattr('fastapi.testclient.TestClient', Client)
    report = baseline.run(manifest, 'development', live, tmp_path / 'report.json', live_vision)
    assert report['mode'] == mode
    assert report['summary']['total_tokens'] == 123
    assert report['runtime']['text_model'] is not None if live else report['runtime']['text_model'] is None
    assert (report['runtime']['vision_model'] is not None) is vision_enabled
    assert not main.DOCUMENT_VAULT
    assert main.DOCUMENT_VAULT is original_vault
    assert os.environ['RAGIT_AUTH_MODE'] == 'clerk'
    assert generator.has_valid_primary_key() and vision.configured()


def test_benchmark_rejects_production(monkeypatch, tmp_path):
    monkeypatch.setenv('RAGIT_ENV', 'production')
    with pytest.raises(ValueError, match='never in production'):
        baseline.run({}, 'development', False, tmp_path / 'report.json')


def test_report_freshness_detects_changed_pipeline_and_legacy_runner():
    report = {
        'pipeline_sha256': baseline.pipeline_sha256(),
        'manifest_sha256': hashlib.sha256((baseline.DATA / 'manifest.json').read_bytes()).hexdigest(),
        'runner_sha256': hashlib.sha256(__import__('pathlib').Path(baseline.__file__).read_bytes()).hexdigest(),
    }
    assert all(baseline.report_freshness(report).values())
    report['pipeline_sha256'] = 'stale'
    del report['runner_sha256']
    assert baseline.report_freshness(report) == {
        'pipeline_matches': False, 'manifest_matches': True, 'runner_matches': False}


def test_live_vision_requires_configured_provider(monkeypatch, tmp_path):
    monkeypatch.setattr(vision, 'configured', lambda: False)
    with pytest.raises(ValueError, match='configured'):
        baseline.run({}, 'development', False, tmp_path / 'report.json', live_vision=True)


def test_pacing_respects_request_start_interval_without_changing_response(monkeypatch):
    now = [0.0]
    starts = []
    monkeypatch.setattr(baseline.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(baseline.time, 'sleep', lambda seconds: now.__setitem__(0, now[0] + seconds))
    def request(value):
        starts.append(now[0])
        now[0] += 2
        return value
    paced = baseline.pace_requests(request, 4)
    assert [paced(value) for value in ('one', 'two', 'three')] == ['one', 'two', 'three']
    assert starts == [0, 15, 30]
