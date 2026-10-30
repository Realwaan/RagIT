import time

import jwt
import numpy as np
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient

from app import auth, config, indexing, main, vault_catalog
from app.ast_builder import DocumentAST
from app.indexing import document_cache_key
from app.processing import ProcessingJobs


@pytest.fixture
def secured(local_pipeline_mode, monkeypatch, tmp_path):
    monkeypatch.setenv('RAGIT_AUTH_MODE', 'clerk')
    monkeypatch.setenv('CLERK_SECRET_KEY', 'test-only-placeholder')
    monkeypatch.setenv('CLERK_AUTHORIZED_PARTIES', 'http://testserver')
    monkeypatch.setattr(config, 'INDEX_DIR', tmp_path)
    monkeypatch.setattr(main, 'PROCESSING_JOBS', ProcessingJobs(tmp_path / 'jobs.sqlite3'))
    monkeypatch.setattr(indexing, 'CACHE_DIR', tmp_path / 'ingestion-cache')
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    monkeypatch.setenv('CLERK_JWT_KEY', public.decode())

    def headers(user='user_alpha', **overrides):
        now = int(time.time())
        payload = {'sub': user, 'sid': 'sess_test', 'iss': 'https://test.clerk.accounts.dev',
                   'azp': 'http://testserver', 'iat': now, 'nbf': now - 1, 'exp': now + 60, **overrides}
        return {'Authorization': 'Bearer ' + jwt.encode(payload, private, algorithm='RS256')}
    return TestClient(main.app), headers


@pytest.mark.parametrize('path', [
    '/vault',
    '/upload-jobs/unknown',
    '/api/ast',
    '/api/ast/doc_' + 'a' * 32,
    '/api/discrepancies?doc_id=doc_' + 'a' * 32,
    '/compliance-audit?doc_id=doc_' + 'a' * 32,
    '/api/crop/doc_' + 'a' * 32 + '/node',
    '/api/preview/doc_' + 'a' * 32 + '/1',
    '/static/previews/doc_' + 'a' * 32 + '_page_1.webp',
    '/static/crops/doc_' + 'a' * 32 + '_node_1.webp',
])
def test_anonymous_requests_rejected(secured, path):
    client, _ = secured
    assert client.get(path).status_code == 401


@pytest.mark.parametrize('overrides', [{'exp': 1}, {'azp': 'https://evil.example'}])
def test_invalid_sessions_rejected(secured, overrides):
    client, headers = secured
    assert client.get('/vault', headers=headers(**overrides)).status_code == 401


def test_processing_status_is_private_and_cancellation_is_owner_only(secured):
    client, headers = secured
    job = main.PROCESSING_JOBS.reserve('user_alpha')
    assert client.get('/upload-jobs/' + job, headers=headers('user_beta')).status_code == 404
    assert client.delete('/upload-jobs/' + job, headers=headers('user_beta')).status_code == 404
    assert not main.PROCESSING_JOBS.active[job][1].is_set()
    result = client.get('/upload-jobs/' + job, headers=headers())
    assert result.status_code == 200
    assert result.headers['cache-control'] == 'private, no-store'
    assert client.delete('/upload-jobs/' + job, headers=headers()).status_code == 200
    assert main.PROCESSING_JOBS.active[job][1].is_set()


def test_tampered_signature_rejected(secured):
    client, headers = secured
    valid = headers()['Authorization']
    tampered = valid[:-4] + ('AAAA' if not valid.endswith('AAAA') else 'BBBB')
    assert client.get('/vault', headers={'Authorization': tampered}).status_code == 401


def test_document_isolation_and_static_bypass(secured, monkeypatch):
    client, headers = secured
    doc_id = 'doc_' + 'a' * 32
    token = auth.current_user.set('user_alpha')
    try:
        auth.grant(doc_id)
    finally:
        auth.current_user.reset(token)

    class AST:
        def to_dict(self): return {'doc_id': doc_id, 'nodes': {}}
        def get_node(self, _): return None

    monkeypatch.setattr(main, 'DOCUMENT_ASTS', {doc_id: AST()})
    monkeypatch.setattr(main, 'DOCUMENT_VAULT', {
        doc_id: {
            'doc_id': doc_id,
            'filename': 'alpha.txt',
            'pages': 1,
            'total_chunks': 1,
            'classification': {'label': 'Test'},
            'uploaded_at': '2026-10-29T00:00:00',
            'ast': AST(),
            'retriever': None,
        }
    })
    res_alpha = client.get('/api/ast/' + doc_id, headers=headers())
    assert res_alpha.status_code == 200
    assert res_alpha.headers.get('cache-control') == 'private, no-store'
    assert client.get('/api/ast?doc_id=' + doc_id, headers=headers()).status_code == 200
    assert client.get('/api/ast?doc_id=' + doc_id, headers=headers('user_beta')).status_code == 404
    assert client.get('/api/ast/' + doc_id, headers=headers('user_beta')).status_code == 404
    paths = [
        f'/api/crop/{doc_id}/node',
        f'/api/preview/{doc_id}/1',
        f'/api/discrepancies?doc_id={doc_id}',
        f'/compliance-audit?doc_id={doc_id}',
        f'/ask-stream?doc_id={doc_id}&query=secret',
        f'/static/previews/{doc_id}_page_1.webp',
        f'/static/crops/{doc_id}_node_1.webp',
        f'/static/assistant/%2e%2e/previews/{doc_id}_page_1.webp',
        f'/assets/%2e%2e/previews/{doc_id}_page_1.webp',
    ]
    for path in paths:
        assert client.get(path, headers=headers('user_beta')).status_code == 404
    assert client.post('/ask', json={'doc_id': doc_id, 'query': 'secret'}, headers=headers('user_beta')).status_code == 404
    assert client.post('/query', json={'doc_id': doc_id, 'query': 'secret'}, headers=headers('user_beta')).status_code == 404
    assert client.post('/api/chat', json={'doc_id': doc_id, 'query': 'secret'}, headers=headers('user_beta')).status_code == 404
    assert client.post('/compliance-audit', json={'doc_id': doc_id, 'framework': 'sla'}, headers=headers('user_beta')).status_code == 404
    assert client.post(f'/vault/select/{doc_id}', headers=headers('user_beta')).status_code == 404
    assert client.get('/classic').status_code == 200
    assert client.post('/api/model/toggle', headers=headers()).status_code == 200
    assert client.post(f'/vault/select/{doc_id}', headers=headers('user_alpha')).status_code == 200

    # User beta's vault must not list user alpha's document
    vault_beta = client.get('/vault', headers=headers('user_beta')).json()
    assert vault_beta['vault'] == []
    vault_alpha = client.get('/vault', headers=headers('user_alpha')).json()
    assert [d['doc_id'] for d in vault_alpha['vault']] == [doc_id]


def test_identical_bytes_different_users_and_restart_isolation(secured, monkeypatch):
    client, headers = secured
    monkeypatch.setattr(main, 'DOCUMENT_VAULT', {})
    monkeypatch.setattr(main, 'DOCUMENT_ASTS', {})

    content = b'# Section 1\nAlpha and Beta upload identical bytes with different names.\nUptime is 99.9%.'
    r_alpha = client.post('/upload', files={'file': ('alpha_copy.txt', content, 'text/plain')}, headers=headers('user_alpha'))
    assert r_alpha.status_code == 200
    doc_alpha = r_alpha.json()['doc_id']

    r_beta = client.post('/upload', files={'file': ('beta_copy.txt', content, 'text/plain')}, headers=headers('user_beta'))
    assert r_beta.status_code == 200
    doc_beta = r_beta.json()['doc_id']

    assert doc_alpha != doc_beta
    assert client.get(f'/api/ast/{doc_alpha}', headers=headers('user_beta')).status_code == 404
    assert client.get(f'/api/ast/{doc_beta}', headers=headers('user_alpha')).status_code == 404

    # Add an unowned legacy document to vault.sqlite3 and verify restore_documents skips it in account mode
    legacy_key = 'f' * 64
    legacy_doc_id = 'doc_' + 'f' * 32
    legacy_ast = DocumentAST(legacy_doc_id, 'legacy.txt')
    indexing._save_cache(
        legacy_key,
        legacy_ast,
        [{'id': 0, 'child_text': 'legacy', 'parent_text': 'legacy', 'page': 1, 'filename': 'legacy.txt'}],
        {'type': 'GENERAL', 'label': 'General'},
        np.ones((1, 4), dtype=np.float32),
        1,
        False,
    )
    vault_catalog.remember_document({
        'doc_id': legacy_doc_id,
        'cache_key': legacy_key,
        'filename': 'legacy.txt',
    })

    restored, unavailable = vault_catalog.restore_documents()
    restored_ids = {entry['doc_id'] for entry in restored}
    assert doc_alpha in restored_ids
    assert doc_beta in restored_ids
    assert legacy_doc_id not in restored_ids
    assert all(u['doc_id'] != legacy_doc_id for u in unavailable)


def test_legacy_utf32_npz_metadata_loads_via_streaming(secured):
    key = 'e' * 64
    doc_id = 'doc_' + 'e' * 32
    ast = DocumentAST(doc_id, 'utf32_legacy.txt')
    chunks = [{'id': 0, 'child_text': 'hello', 'parent_text': 'hello', 'page': 1, 'filename': 'utf32_legacy.txt'}]
    vectors = np.ones((1, 4), dtype=np.float32)
    indexing.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # Save using legacy Unicode string array (<U...) format
    import json as _json
    metadata_str = _json.dumps({
        'key': key, 'ast': ast.to_dict(), 'chunks': chunks,
        'classification': {'type': 'GENERAL', 'label': 'General'}, 'pages': 1, 'is_pdf': False,
    })
    np.savez_compressed(indexing.CACHE_DIR / f'{key}.npz', metadata=metadata_str, vectors=vectors)
    loaded = indexing._load_cache(key)
    assert loaded is not None
    assert loaded[0].doc_id == doc_id


def test_production_config_fails_closed(monkeypatch):
    monkeypatch.setenv('RAGIT_ENV', 'production')
    monkeypatch.setenv('RAGIT_AUTH_MODE', 'local')
    with pytest.raises(RuntimeError, match='RAGIT_AUTH_MODE=local is forbidden'):
        auth.validate_auth_config()

    monkeypatch.setenv('RAGIT_AUTH_MODE', 'clerk')
    monkeypatch.setenv('CLERK_SECRET_KEY', 'sk_test_dev_key')
    with pytest.raises(RuntimeError, match='live CLERK_SECRET_KEY'):
        auth.validate_auth_config()

    monkeypatch.setenv('CLERK_SECRET_KEY', 'sk_live_prod_key')
    monkeypatch.setenv('CLERK_AUTHORIZED_PARTIES', 'http://insecure.example.com')
    with pytest.raises(RuntimeError, match='HTTPS CLERK_AUTHORIZED_PARTIES'):
        auth.validate_auth_config()


def test_cache_identity_scoped_to_account(secured):
    def key(user):
        token = auth.current_user.set(user)
        try: return document_cache_key(b'same document', 'same.txt')
        finally: auth.current_user.reset(token)
    assert key('user_alpha') == key('user_alpha')
    assert key('user_alpha') != key('user_beta')


def test_rate_limiting_and_ingress_limits(secured, monkeypatch):
    client, headers = secured
    monkeypatch.setenv('RAGIT_RATE_LIMIT_PER_MIN', '3')
    auth._USER_REQUEST_TIMES.clear()
    assert client.get('/vault', headers=headers('user_rate')).status_code == 200
    assert client.get('/vault', headers=headers('user_rate')).status_code == 200
    assert client.get('/vault', headers=headers('user_rate')).status_code == 200
    assert client.get('/vault', headers=headers('user_rate')).status_code == 429
    # Other users are unaffected
    assert client.get('/vault', headers=headers('user_other')).status_code == 200


def test_provider_outage_returns_503(secured, monkeypatch):
    client, headers = secured
    def broken_auth(*args, **kwargs):
        raise RuntimeError('Upstream JWKS timeout')
    monkeypatch.setattr(auth, 'authenticate_request', broken_auth)
    res = client.get('/vault', headers=headers('user_alpha'))
    assert res.status_code == 503
    assert 'temporarily unavailable' in res.json()['detail']


def test_health_reveals_no_document_metadata(secured):
    client, _ = secured
    assert client.get('/health').json() == {'status': 'healthy'}


def test_public_readiness_has_no_document_data_and_tracks_dependencies(secured, monkeypatch):
    client, _ = secured
    for key in ('accepting_requests', 'embedding_preload_succeeded', 'storage_ready'):
        monkeypatch.setattr(main.app.state, key, True, raising=False)
    monkeypatch.setattr(main.app.state, 'vault_recovery', {'status': 'ready'}, raising=False)
    assert client.get('/ready').json() == {'status': 'ready'}
    monkeypatch.setattr(main.app.state, 'storage_ready', False)
    response = client.get('/ready')
    assert response.status_code == 503
    assert response.json() == {'status': 'not_ready'}


@pytest.mark.parametrize('secret', ['', 'placeholder', 'sk_test_development', 'pk_live_public', 'sk_live_'])
def test_production_rejects_non_live_secret_format(monkeypatch, secret):
    monkeypatch.setenv('RAGIT_ENV', 'production')
    monkeypatch.setenv('RAGIT_AUTH_MODE', 'clerk')
    monkeypatch.setenv('CLERK_SECRET_KEY', secret)
    monkeypatch.setenv('CLERK_AUTHORIZED_PARTIES', 'https://example.com')
    with pytest.raises(RuntimeError, match='live CLERK_SECRET_KEY'):
        auth.validate_auth_config()


@pytest.mark.parametrize('origin', ['ftp://example.com', 'https://example.com/path', 'https://user:password@example.com', 'https://', 'https://example.com?query=1'])
def test_production_rejects_non_origin_allowlist(monkeypatch, origin):
    monkeypatch.setenv('RAGIT_ENV', 'production')
    monkeypatch.setenv('RAGIT_AUTH_MODE', 'clerk')
    monkeypatch.setenv('CLERK_SECRET_KEY', 'sk_live_test_fixture')
    monkeypatch.setenv('CLERK_AUTHORIZED_PARTIES', origin)
    with pytest.raises(RuntimeError, match='HTTPS'):
        auth.validate_auth_config()


def test_delete_and_upload_cannot_mutate_storage_concurrently(secured, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    client, headers = secured
    doc_id = 'doc_' + 'e' * 32
    token = auth.current_user.set('user_alpha')
    try:
        auth.grant(doc_id)
    finally:
        auth.current_user.reset(token)
    main.DOCUMENT_VAULT[doc_id] = {'doc_id': doc_id}
    reservation = main.PROCESSING_JOBS.reserve('user_alpha')
    assert client.delete('/vault/' + doc_id, headers=headers()).status_code == 429
    assert doc_id in main.DOCUMENT_VAULT
    main.PROCESSING_JOBS.release(reservation)
    entered, release = Event(), Event()

    def forget(*args):
        entered.set()
        assert release.wait(10)
        return True

    monkeypatch.setattr(main, 'forget_document', forget)
    with ThreadPoolExecutor() as executor:
        deletion = executor.submit(client.delete, '/vault/' + doc_id, headers=headers())
        try:
            assert entered.wait(5)
            result = client.post('/upload-jobs', headers=headers(), files={'file': ('retry.txt', b'text')})
            assert result.status_code == 429
        finally:
            release.set()
        assert deletion.result(timeout=5).status_code == 200
    assert not main.PROCESSING_JOBS.active


def test_delete_vault_document(secured):
    client, headers = secured
    doc_id = 'doc_' + 'f' * 32
    token = auth.current_user.set('user_alpha')
    try:
        auth.grant(doc_id)
    finally:
        auth.current_user.reset(token)

    main.DOCUMENT_VAULT[doc_id] = {'doc_id': doc_id, 'filename': 'secret.txt', 'cache_key': 'f' * 64}
    main.DOCUMENT_ASTS[doc_id] = object()

    # Anonymous delete rejected with 401
    assert client.delete(f'/vault/{doc_id}').status_code == 401

    # Non-owner user_beta rejected with 404
    assert client.delete(f'/vault/{doc_id}', headers=headers('user_beta')).status_code == 404

    # Owner user_alpha deletes successfully
    del_res = client.delete(f'/vault/{doc_id}', headers=headers('user_alpha'))
    assert del_res.status_code == 200
    assert del_res.json() == {'ok': True, 'doc_id': doc_id}

    # Document is gone from memory and cannot be deleted again
    assert doc_id not in main.DOCUMENT_VAULT
    assert doc_id not in main.DOCUMENT_ASTS
    assert client.delete(f'/vault/{doc_id}', headers=headers('user_alpha')).status_code == 404


