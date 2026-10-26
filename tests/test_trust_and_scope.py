import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.evaluator import evaluate_relevance, verify_generated_answer


@pytest.mark.parametrize('answer,expected', [
    ('The load is 40 kg. [1]', 'supported'),
    ('The load is 90 kg. [1]', 'uncertain'),
    ('The load is 40 kg.', 'unsupported'),
    ('The load is 40 kg. [9]', 'unsupported'),
    ('The load is 40 kg. [1] The building is insured. [1]', 'uncertain'),
])
def test_claim_support_is_separate_from_citation_validity(answer, expected):
    chunks = [{'citation_id': 1, 'parent_text': 'The load is 40 kg.', 'dense_score': .9}]
    result = verify_generated_answer(answer, chunks, evaluate_relevance(chunks))
    assert result['claims'][-1]['status'] == expected
    assert result['claim_support'] == ('supported' if expected == 'supported' else 'needs_review')
    if '90' in answer:
        assert result['citation_verified'] is True
        assert result['claim_support'] != 'supported'


@pytest.mark.parametrize('source', ['The load is not 40 kg.', 'The load is 40 kg only if approved.'])
def test_dropping_negation_or_conditions_is_not_supported(source):
    result = verify_generated_answer('The load is 40 kg. [1]', [{'parent_text': source}], {})
    assert result['claims'][0]['status'] == 'uncertain'


@pytest.fixture
def documents(monkeypatch):
    barrier = threading.Barrier(2)
    class Retriever:
        def __init__(self, name):
            self.name = name
        def retrieve(self, query, top_k):
            if query == 'concurrent':
                barrier.wait(timeout=10)
            return [{'citation_id': 1, 'parent_text': f'The owner is {self.name}.',
                     'child_text': f'The owner is {self.name}.', 'dense_score': .95,
                     'page': 1, 'filename': self.name}]
    vault = {name: {'retriever': Retriever(name), 'filename': name,
                    'classification': {}, 'ast': None} for name in ('alpha', 'beta')}
    monkeypatch.setattr(main, 'DOCUMENT_VAULT', vault)
    monkeypatch.setattr(main, 'ACTIVE_DOC_ID', 'beta')
    monkeypatch.setattr(main, 'visual_answer', lambda *args: None)
    monkeypatch.setattr(main, 'generate_grounded_answer_with_telemetry',
        lambda q, chunks, p: (chunks[0]['parent_text'] + ' [1]', {}))
    monkeypatch.setattr(main, 'stream_grounded_answer',
        lambda q, chunks, p, **kw: iter([chunks[0]['parent_text'] + ' [1]']))
    return vault


@pytest.mark.parametrize('endpoint', ['/ask', '/query', '/api/chat', '/ask-stream',
                                      '/compliance-audit', '/api/discrepancies', '/api/ast/discrepancies'])
def test_explicit_document_required_and_unknown_never_falls_back(documents, endpoint):
    client = TestClient(main.app)
    if endpoint in ('/ask', '/query', '/api/chat'):
        missing = client.post(endpoint, json={'query': 'owner'})
        unknown = client.post(endpoint, json={'query': 'owner', 'doc_id': 'missing'})
    else:
        missing = client.get(endpoint, params={'query': 'owner'})
        unknown = client.get(endpoint, params={'query': 'owner', 'doc_id': 'missing'})
    assert missing.status_code == 422
    assert unknown.status_code == 404


def test_concurrent_requests_keep_their_own_sources(documents):
    def ask(name):
        return TestClient(main.app).post('/ask', json={'query': 'concurrent', 'doc_id': name}).json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(ask, ['alpha', 'beta']))
    for name, result in zip(['alpha', 'beta'], results):
        assert result['doc_id'] == name
        assert result['sources'][0]['filename'] == name
        assert result['answer'] == f'The owner is {name}. [1]'


def test_audit_switch_does_not_change_report_identity(documents, monkeypatch):
    def audit(retriever):
        main.ACTIVE_DOC_ID = 'beta'
        return {'owner': retriever.name}
    monkeypatch.setattr(main, 'run_compliance_audit', audit)
    result = TestClient(main.app).get('/compliance-audit', params={'doc_id': 'alpha'}).json()
    assert result['owner'] == result['filename'] == result['doc_id'] == 'alpha'


def test_discrepancy_switch_does_not_change_report_identity(documents, monkeypatch):
    documents['alpha']['ast'] = SimpleNamespace(doc_id='alpha')
    def scan(ast, use_llm):
        main.ACTIVE_DOC_ID = 'beta'
        return {'scanned': ast.doc_id}
    monkeypatch.setattr(main, 'scan_ast_for_discrepancies', scan)
    result = TestClient(main.app).get('/api/discrepancies', params={'doc_id': 'alpha'}).json()
    assert result['scanned'] == result['filename'] == result['doc_id'] == 'alpha'


def test_baseline_split_and_metrics():
    import json
    from scripts.document_baseline import DATA, summarize
    manifest = json.loads((DATA / 'manifest.json').read_text())
    assert len(manifest['cases']) == 150
    sets = [{c['document'] for c in manifest['cases'] if c['split'] == split}
            for split in ('development', 'held_out')]
    assert not sets[0] & sets[1]
    assert len({c['id'] for c in manifest['cases']}) == 150
    assert summarize([])['answer_correctness'] is None
    assert summarize([])['expected_answer_match_rate'] is None


def test_review_requires_complete_matching_answers():
    from scripts.document_baseline import apply_review, summarize
    row = {'id': 'one', 'category': 'native', 'answer_sha256': 'current',
           'answerable': True, 'refused': False, 'page_recall_at_10': 1,
           'expected_answer_match': True, 'citation_page_match': True,
           'latency_ms': 1, 'tokens': 0}
    report = {'checks': [row], 'summary': summarize([row]),
              'by_category': {'native': summarize([row])}}
    with pytest.raises(ValueError, match='Missing review'):
        apply_review(report, {})
    review = {'answer_sha256': 'old', 'answer_correct': True, 'citation_correct': True,
              'invented_number': False, 'supported_claims': 1, 'total_claims': 1}
    with pytest.raises(ValueError, match='Stale review'):
        apply_review(report, {'one': review})
    review['answer_sha256'] = 'current'
    assert apply_review(report, {'one': review})['release_gate'] == 'passed'
    review['invented_number'] = True
    assert apply_review(report, {'one': review})['release_gate'] == 'failed'


@pytest.mark.parametrize('endpoint', ['/api/chat', '/ask-stream'])
def test_streams_keep_explicit_document_and_final_checks(documents, endpoint):
    import json
    client = TestClient(main.app)
    if endpoint == '/ask-stream':
        response = client.get(endpoint, params={'query': 'owner', 'doc_id': 'alpha'})
        assert response.headers['X-Document-ID'] == 'alpha'
        assert response.text == 'The owner is alpha. [1]'
    else:
        response = client.post(endpoint, json={'query': 'owner', 'doc_id': 'alpha'})
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        assert all(event['doc_id'] == 'alpha' for event in events)
        assert events[-1]['evaluation']['claim_support'] == 'supported'
        assert events[-1]['sources'][0]['filename'] == 'alpha'
