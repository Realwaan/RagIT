"""Exercise durable document identity and restart recovery using real cache files."""
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import config as cfg, indexing, main, vault_catalog


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(indexing, 'CACHE_DIR', tmp_path / 'cache')
    monkeypatch.setattr(indexing, 'embed_texts',
                        lambda texts: np.ones((len(texts), 384), dtype=np.float32))
    monkeypatch.setattr(main, 'get_embedding_model', lambda: object())
    monkeypatch.setattr(main, 'DOCUMENT_VAULT', {})
    monkeypatch.setattr(main, 'DOCUMENT_ASTS', {})
    monkeypatch.setattr(main, 'ACTIVE_DOC_ID', '')
    monkeypatch.setattr(main, 'ACTIVE_RETRIEVER', None)
    monkeypatch.setattr(main, 'ACTIVE_CHUNKS', [])
    monkeypatch.setattr(main, 'ACTIVE_CLASSIFICATION', {})
    worker = SimpleNamespace(submit=lambda ast: {'status': 'ready'}, shutdown=lambda: None,
                             snapshot=lambda state: state, status=lambda doc_id: {'status': 'ready'})
    monkeypatch.setattr(main, 'BACKGROUND_INDEXER', worker)
    monkeypatch.setattr(main, 'VISUAL_INDEXER', worker)


def prepare(name='policy.txt', contents=b'The retention period is 42 days.'):
    return indexing.prepare_document(contents, name)


def test_restore_only_registered_documents_and_latest_filename(isolated, monkeypatch):
    entry = prepare()
    vault_catalog.remember_document(entry)
    renamed = prepare('renamed.md')
    vault_catalog.remember_document(renamed)
    prepare('benchmark.txt', b'The deadline is Friday.')
    monkeypatch.setattr(indexing, 'embed_texts', lambda *args: pytest.fail('Recovery re-embedded text'))
    restored, unavailable = vault_catalog.restore_documents()
    assert not unavailable and len(restored) == 1
    result = restored[0]
    assert result['doc_id'] == entry['doc_id']
    assert result['filename'] == result['ast'].title == 'renamed.md'
    assert all(chunk['filename'] == 'renamed.md' for chunk in result['chunks'])
    np.testing.assert_array_equal(result['retriever'].embeddings, entry['retriever'].embeddings)


@pytest.mark.parametrize('damage', ['missing', 'corrupt', 'model', 'pipeline', 'identity'])
def test_unavailable_documents_are_reported(isolated, monkeypatch, damage):
    entry = prepare()
    vault_catalog.remember_document(entry)
    path = indexing.CACHE_DIR / f"{entry['cache_key']}.npz"
    if damage == 'missing':
        path.unlink()
    elif damage == 'corrupt':
        path.write_bytes(b'incomplete')
    elif damage == 'model':
        monkeypatch.setattr(cfg, 'DEFAULT_EMBED_MODEL', 'different-model')
    elif damage == 'pipeline':
        monkeypatch.setattr(indexing, 'PIPELINE_VERSION', 'different-version')
    else:
        with vault_catalog.connection() as database:
            database.execute('UPDATE documents SET cache_key=?', ('../invalid',))
    restored, unavailable = vault_catalog.restore_documents()
    assert not restored
    assert unavailable[0]['doc_id'] == entry['doc_id']
    assert unavailable[0]['reason'] == {
        'missing': 'cache_or_source_unavailable', 'corrupt': 'cache_or_source_unavailable',
        'model': 'configuration_changed', 'pipeline': 'configuration_changed',
        'identity': 'invalid_identity',
    }[damage]


def test_one_unusable_retriever_does_not_block_other_documents(isolated, monkeypatch):
    for entry in (prepare(), prepare('second.txt', b'The deadline is Friday.')):
        vault_catalog.remember_document(entry)
    constructor = vault_catalog.HybridRetriever
    def restore(chunks, vectors):
        if chunks[0]['filename'] == 'policy.txt':
            raise ValueError('invalid cached search data')
        return constructor(chunks, vectors)
    monkeypatch.setattr(vault_catalog, 'HybridRetriever', restore)
    restored, unavailable = vault_catalog.restore_documents()
    assert [entry['filename'] for entry in restored] == ['second.txt']
    assert unavailable[0]['reason'] == 'invalid_cached_document'


def test_upload_and_restart_restores_document_without_reattachment(isolated):
    with TestClient(main.app) as client:
        response = client.post('/upload', files={'file': ('policy.txt', b'The retention period is 42 days.')})
        assert response.status_code == 200
        doc_id = response.json()['doc_id']
    main.DOCUMENT_VAULT.clear()
    main.DOCUMENT_ASTS.clear()
    main.ACTIVE_DOC_ID = ''
    main.ACTIVE_RETRIEVER = None
    main.ACTIVE_CHUNKS = []
    with TestClient(main.app) as client:
        vault = client.get('/vault').json()
        assert vault['active_doc_id'] == doc_id
        assert vault['recovery'] == {'restored': 1, 'unavailable': [], 'status': 'ready'}
        assert vault['vault'][0]['restored'] is True
        assert main.document_snapshot(doc_id)['retriever'].bm25 is not None
        assert client.get('/api/ast').json()['doc_id'] == doc_id


def test_vault_capacity_rejects_new_document_but_allows_existing(isolated, monkeypatch):
    monkeypatch.setattr(cfg, 'MAX_VAULT_DOCUMENTS', 1)
    with TestClient(main.app) as client:
        first = client.post('/upload', files={'file': ('policy.txt', b'The retention period is 42 days.')})
        assert first.status_code == 200
        caches_before = set(indexing.CACHE_DIR.glob('*.npz'))
        rejected = client.post('/upload', files={'file': ('other.txt', b'The deadline is Friday.')})
        assert rejected.status_code == 507
        assert set(indexing.CACHE_DIR.glob('*.npz')) == caches_before
        assert len(main.DOCUMENT_VAULT) == 1
        assert client.post('/upload', files={'file': ('policy.txt', b'The retention period is 42 days.')}).status_code == 200
        assert len(vault_catalog.restore_documents()[0]) == 1


def test_passage_capacity_rejection_cleans_new_ingestion_cache(isolated, monkeypatch):
    monkeypatch.setattr(cfg, 'MAX_VAULT_CHUNKS', 1)
    with TestClient(main.app) as client:
        first = client.post('/upload', files={'file': ('one.txt', b'First policy.')})
        assert first.status_code == 200
        before = set(indexing.CACHE_DIR.glob('*.npz'))
        response = client.post('/upload', files={'file': ('two.txt', b'Second policy.')})
        assert response.status_code == 507
        assert set(indexing.CACHE_DIR.glob('*.npz')) == before
        assert len(main.DOCUMENT_VAULT) == 1


def test_restore_capacity_reports_unloaded_documents_without_erasing_catalog(isolated, monkeypatch):
    for text in (b'First policy.', b'Second policy.'):
        vault_catalog.remember_document(prepare(contents=text))
    monkeypatch.setattr(cfg, 'MAX_VAULT_DOCUMENTS', 1)
    restored, unavailable = vault_catalog.restore_documents()
    assert len(restored) == len(unavailable) == 1
    assert unavailable[0]['reason'] == 'server_capacity'
    monkeypatch.setattr(cfg, 'MAX_VAULT_DOCUMENTS', 2)
    assert len(vault_catalog.restore_documents()[0]) == 2
    monkeypatch.setattr(cfg, 'MAX_VAULT_CHUNKS', 1)
    restored, unavailable = vault_catalog.restore_documents()
    assert sum(e['total_chunks'] for e in restored) <= 1
    assert unavailable


def test_catalog_write_failure_keeps_upload_searchable(isolated, monkeypatch):
    def fail(entry):
        raise OSError('disk full')
    monkeypatch.setattr(main, 'remember_document', fail)
    with TestClient(main.app) as client:
        response = client.post('/upload', files={'file': ('policy.txt', b'The retention period is 42 days.')})
        assert response.status_code == 200
        result = response.json()
        assert 'reattachment' in result['cache_warning']
        assert main.document_snapshot(result['doc_id'])['retriever'].bm25 is not None


def test_catalog_failure_does_not_prevent_startup(isolated, monkeypatch):
    def fail():
        raise OSError('unreadable catalog')
    monkeypatch.setattr(main, 'restore_documents', fail)
    with TestClient(main.app) as client:
        assert client.get('/health').json()['vault_recovery']['status'] == 'failed'
        assert client.post('/upload', files={'file': ('policy.txt', b'The deadline is Friday.')}).status_code == 200
