import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient

from app import auth, config, main
from app.indexing import document_cache_key


@pytest.fixture
def secured(local_pipeline_mode, monkeypatch, tmp_path):
    monkeypatch.setenv('RAGIT_AUTH_MODE', 'clerk')
    monkeypatch.setenv('CLERK_SECRET_KEY', 'test-only-placeholder')
    monkeypatch.setenv('CLERK_AUTHORIZED_PARTIES', 'http://testserver')
    monkeypatch.setattr(config, 'INDEX_DIR', tmp_path)
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    monkeypatch.setenv('CLERK_JWT_KEY', public.decode())

    def headers(user='user_alpha', **overrides):
        now = int(time.time())
        payload = {'sub': user, 'sid': 'sess_test', 'iss': 'https://test.clerk.accounts.dev',
                   'azp': 'http://testserver', 'iat': now, 'nbf': now - 1, 'exp': now + 60, **overrides}
        return {'Authorization': 'Bearer ' + jwt.encode(payload, private, algorithm='RS256')}
    return TestClient(main.app), headers


@pytest.mark.parametrize('path', ['/vault', '/api/ast', '/api/preview/doc_fake/1', '/static/previews/doc_fake_page_1.webp'])
def test_anonymous_requests_rejected(secured, path):
    client, _ = secured
    assert client.get(path).status_code == 401


@pytest.mark.parametrize('overrides', [{'exp': 1}, {'azp': 'https://evil.example'}])
def test_invalid_sessions_rejected(secured, overrides):
    client, headers = secured
    assert client.get('/vault', headers=headers(**overrides)).status_code == 401


def test_document_isolation_and_static_bypass(secured, monkeypatch):
    client, headers = secured
    doc_id = 'doc_' + 'a' * 32
    token = auth.current_user.set('user_alpha')
    try:
        auth.grant(doc_id)
    finally:
        auth.current_user.reset(token)
    class AST:
        def to_dict(self): return {'doc_id': doc_id}
    monkeypatch.setattr(main, 'DOCUMENT_ASTS', {doc_id: AST()})
    assert client.get('/api/ast/' + doc_id, headers=headers()).status_code == 200
    assert client.get('/api/ast/' + doc_id, headers=headers('user_beta')).status_code == 404
    paths = [f'/api/crop/{doc_id}/node', f'/api/preview/{doc_id}/1',
             f'/static/previews/{doc_id}_page_1.webp',
             f'/static/assistant/%2e%2e/previews/{doc_id}_page_1.webp']
    for path in paths:
        assert client.get(path, headers=headers('user_beta')).status_code == 404
    assert client.post('/ask', json={'doc_id': doc_id, 'query': 'secret'}, headers=headers('user_beta')).status_code == 404
    assert client.get('/classic', headers=headers()).status_code == 403


def test_cache_identity_scoped_to_account(secured):
    def key(user):
        token = auth.current_user.set(user)
        try: return document_cache_key(b'same document', 'same.txt')
        finally: auth.current_user.reset(token)
    assert key('user_alpha') == key('user_alpha')
    assert key('user_alpha') != key('user_beta')


def test_health_reveals_no_document_metadata(secured):
    client, _ = secured
    assert client.get('/health').json() == {'status': 'healthy'}
