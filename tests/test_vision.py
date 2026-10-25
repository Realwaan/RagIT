"""Deterministic safety and integration checks; no external model calls."""
import io
import json
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.vision as vision
from app.ast_builder import ASTNode, ASTNodeType, DocumentAST


@pytest.fixture
def ast(monkeypatch):
    tree = DocumentAST('doc_test', 'pictures.pdf')
    for i in range(1, 10):
        tree.add_node(ASTNode(f'v{i}', ASTNodeType.VISUAL, f'Figure {i}: Example',
                              'Visible labels', i, f'root/v{i}', bbox=(0, 0, 100, 100),
                              image_url=f'/api/crop/doc_test/v{i}', visual_type='figure'))
    monkeypatch.setattr(vision, 'configured', lambda: True)
    monkeypatch.setattr(vision.VISUAL_INDEXER, 'search', lambda *args: [])
    monkeypatch.setattr(vision, 'image_evidence', lambda ast, node: [(node.id, b'image')])
    return tree


def draft(text='The arrow points to B.', ids=None):
    return vision.Draft(claims=[vision.Claim(text=text, source_ids=ids or [1])], insufficient=False)


def mock_calls(monkeypatch, *responses):
    calls = []
    values = iter(responses)
    def call(prompt, images, schema):
        calls.append((prompt, images, schema))
        value = next(values)
        if isinstance(value, Exception):
            raise value
        return value, {'total_tokens': 10}
    monkeypatch.setattr(vision, 'call_vision', call)
    return calls


def test_checked_answer_has_exact_image_identity(ast, monkeypatch):
    calls = mock_calls(monkeypatch, draft(), vision.Verification(verdicts=[
        vision.Verdict(claim_index=0, supported=True, reason='Visible arrowhead')]))
    result = vision.visual_answer(ast, 'Explain Figure 4 on PDF page 4', [])
    assert result['answer'] == 'The arrow points to B. [1]'
    assert result['sources'][0]['visual_id'] == 'v4'
    assert result['sources'][0]['page'] == 4
    assert result['sources'][0]['verification_status'] == 'model_checked'
    assert result['evaluation']['visual_support'] == 'model_checked'
    assert 'confidence' not in result['evaluation']
    assert len(calls) == 2 and result['token_telemetry']['total_tokens'] == 20


@pytest.mark.parametrize('verdicts', [[], [False], [True, True], [False, True]])
def test_rejected_missing_or_duplicate_verdict_cannot_publish(ast, monkeypatch, verdicts):
    mock_calls(monkeypatch, draft(), vision.Verification(verdicts=[
        vision.Verdict(claim_index=0, supported=v, reason='check') for v in verdicts]))
    result = vision.visual_answer(ast, 'Explain Figure 1', [])
    assert result['status'] == 'REFUSE'
    assert result['sources'] == []


@pytest.mark.parametrize('claim', [draft(ids=[99]), draft(text='Invented source [2]')])
def test_invalid_claim_citations_are_rejected_before_verification(ast, monkeypatch, claim):
    calls = mock_calls(monkeypatch, claim)
    assert vision.visual_answer(ast, 'Explain Figure 1', [])['status'] == 'REFUSE'
    assert len(calls) == 1


def test_only_supported_claims_are_published(ast, monkeypatch):
    response = vision.Draft(claims=[draft().claims[0], vision.Claim(text='The value is 999.', source_ids=[1])], insufficient=False)
    mock_calls(monkeypatch, response, vision.Verification(verdicts=[
        vision.Verdict(claim_index=0, supported=True, reason='Visible'),
        vision.Verdict(claim_index=1, supported=False, reason='Not shown')]))
    result = vision.visual_answer(ast, 'Explain Figure 1', [])
    assert '999' not in result['answer']
    assert 'could not be verified' in result['answer']


def test_provider_failure_does_not_leak_draft(ast, monkeypatch):
    mock_calls(monkeypatch, draft(), TimeoutError('provider timeout'))
    result = vision.visual_answer(ast, 'Explain Figure 1', [])
    assert result['status'] == 'REFUSE'
    assert 'arrow' not in result['answer']
    assert result['evaluation']['visual_support'] == 'unavailable'


def test_selection_obeys_figure_number_and_page(ast):
    assert [v.id for v in vision.select_visuals(ast, 'Figure 1 on PDF page 1', [])] == ['v1']
    assert vision.select_visuals(ast, 'Figure 1 on PDF page 8', []) == []
    assert vision.select_visuals(ast, 'Figure 10', []) == []
    assert vision.visual_answer(ast, 'Figure 10', [])['status'] == 'REFUSE'


def test_unlabeled_visual_found_by_description(ast, monkeypatch):
    ast.get_node('v3').title = 'Uncaptioned visual'
    monkeypatch.setattr(vision.VISUAL_INDEXER, 'search', lambda *args: [{'ast_node_id': 'v3', 'dense_score': .8}])
    assert [n.id for n in vision.select_visuals(ast, 'Where does the blue pipe lead?', [])] == ['v3']


def test_expansion_is_bounded_and_requires_insufficient_evidence(ast, monkeypatch):
    hits = [{'ast_node_id': f'v{i}'} for i in range(1, 10)]
    calls = mock_calls(monkeypatch, vision.Draft(claims=[], insufficient=True), draft(),
                       vision.Verification(verdicts=[vision.Verdict(claim_index=0, supported=True, reason='visible')]))
    result = vision.visual_answer(ast, 'Explain these pictures', hits)
    assert result['status'] == 'SUCCESS'
    assert [len(c[1]) for c in calls] == [4, 8, 8]


def test_native_table_lookup_skips_vision(ast, monkeypatch):
    monkeypatch.setattr(vision, 'call_vision', lambda *args: pytest.fail('Unnecessary vision call'))
    hits = [{'parent_text': '| Region | Value |\n| --- | --- |\n| North | 42 |'}]
    assert vision.visual_answer(ast, 'North Value', hits) is None


def test_no_credentials_never_calls_provider(ast, monkeypatch):
    monkeypatch.setattr(vision, 'configured', lambda: False)
    monkeypatch.setattr(vision, 'call_vision', lambda *args: pytest.fail('External call'))
    result = vision.visual_answer(ast, 'Explain Figure 1', [])
    assert result['evaluation']['visual_support'] == 'unavailable'
    assert result['status'] == 'REFUSE'


def test_description_cache_invalidates_on_context_model_and_image(ast, monkeypatch, tmp_path):
    monkeypatch.setattr(vision, 'CACHE_DIR', tmp_path)
    description = vision.Description(summary='Blue circle', labels=[], relationships=[], values_and_units=[], uncertainties=[])
    calls = mock_calls(monkeypatch, description, description, description, description)
    node = ast.get_node('v1')
    vision.describe(ast, node)
    assert vision.describe(ast, node)[1]['cached']
    node.text = 'Different caption'
    vision.describe(ast, node)
    monkeypatch.setattr(vision.cfg, 'VISION_MODEL', 'different-model')
    vision.describe(ast, node)
    monkeypatch.setattr(vision, 'image_evidence', lambda *a: [('crop', b'changed pixels')])
    vision.describe(ast, node)
    assert len(calls) == 4


def test_partial_background_job_publishes_snapshot_and_retry(ast, monkeypatch):
    tree = DocumentAST('doc_test', 'pictures.pdf')
    tree.add_node(ast.get_node('v1'))
    tree.add_node(ast.get_node('v2'))
    description = vision.Description(summary='Visible blue circle', labels=[], relationships=[], values_and_units=[], uncertainties=[])
    failed = [True]
    def describe(ast, node):
        if node.id == 'v2' and failed[0]:
            raise ValueError('unreadable')
        return description, {'total_tokens': 3}
    monkeypatch.setattr(vision, 'describe', describe)
    monkeypatch.setattr(vision, 'embed_texts', lambda texts: np.array([[1., 0.]] * len(texts)))
    indexer = vision.VisualIndexer()
    indexer.submit(tree)
    indexer.shutdown()
    assert indexer.status(tree.doc_id)['status'] == 'partial'
    assert indexer.status(tree.doc_id)['completed'] == 1
    first = indexer.snapshots[tree.doc_id]
    failed[0] = False
    indexer.submit(tree)
    indexer.shutdown()
    assert indexer.status(tree.doc_id)['completed'] == 2
    assert len(first.chunks) == 1  # Already-running questions keep an immutable snapshot.
    assert len(indexer.snapshots[tree.doc_id].chunks) == 2


def test_sync_and_stream_return_same_checked_result(ast, monkeypatch):
    import app.main as main
    class Retriever:
        def retrieve(self, *args):
            return []
    result = vision._result('Blue circle. [1]', [{**vision.source_for(ast, ast.get_node('v1')), 'citation_id': 1}], 4, vision.time.perf_counter(), 'model_checked')
    monkeypatch.setattr(main, 'visual_answer', lambda *a: result)
    entry = {'retriever': Retriever(), 'ast': ast, 'classification': {}}
    monkeypatch.setattr(main, 'DOCUMENT_VAULT', {ast.doc_id: entry})
    monkeypatch.setattr(main, 'ACTIVE_DOC_ID', ast.doc_id)
    client = TestClient(main.app)
    response = client.post('/ask', json={'query': 'Explain Figure 1'})
    assert response.status_code == 200
    assert response.json()['answer'] == result['answer']
    response = client.post('/api/chat', json={'query': 'Explain Figure 1', 'doc_id': ast.doc_id})
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert events[-1]['answer'] == result['answer']
    assert events[-1]['sources'] == json.loads(json.dumps(result['sources']))
    assert next(e for e in events if e['type'] == 'delta')['text'] == result['answer']


def test_image_only_pdf_is_search_ready_without_ocr(monkeypatch, tmp_path):
    import app.ast_builder as builder
    import app.ingest as ingest
    import app.indexing as indexing
    for name in ('DOCS_DIR', 'PREVIEWS_DIR', 'CROPS_DIR'):
        directory = tmp_path / name
        directory.mkdir()
        for module in (vision.cfg, builder, ingest):
            if hasattr(module, name):
                monkeypatch.setattr(module, name, directory)
    monkeypatch.setattr(indexing, 'CACHE_DIR', tmp_path / 'cache')
    monkeypatch.setattr(ingest, 'recognize_image', lambda image: [])
    monkeypatch.setattr(indexing, 'embed_texts', lambda texts: np.array([[1., 0.]] * len(texts)))
    image = Image.new('RGB', (300, 300), 'blue')
    output = io.BytesIO()
    image.save(output, format='PDF')
    image.close()
    prepared = indexing.prepare_document(output.getvalue(), 'unlabeled.pdf')
    assert prepared['pages'] == 1
    assert prepared['chunks']
    assert prepared['ast'].get_visual_nodes()[0].metadata['crop_scope'] == 'full_page'
    assert indexing.prepare_document(output.getvalue(), 'renamed.pdf')['cache_hit']


def test_scanned_caption_resolves_to_its_page(monkeypatch):
    import app.ast_builder as builder
    node = ASTNode('v', ASTNodeType.VISUAL, 'Uncaptioned', '', 1, 'root/v',
                   bbox=(0, 0, 100, 100), metadata={'crop_scope': 'full_page'})
    monkeypatch.setattr(builder, 'extract_halo_crops', lambda *a, **kw: [node])
    tree = builder.build_document_ast('doc_test', [{'page': 1, 'filename': 'scan.pdf',
        'text': 'Figure 1: Pump routing\nArrow points toward outlet.'}], pdf_bytes=b'placeholder', lazy_visuals=True)
    assert [n.id for n in vision.select_visuals(tree, 'Explain Figure 1 on PDF page 1', [])] == ['v']


def test_provider_request_contains_images_and_schema(monkeypatch):
    recorded = {}
    def create(**kwargs):
        recorded.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=
            '{"claims": [], "insufficient": true}'))], usage=SimpleNamespace(total_tokens=17))
    monkeypatch.setattr(vision, 'OpenAI', lambda **kw: SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=create))))
    result, usage = vision.call_vision('Question', [('Source [1]', b'pixels')], vision.Draft)
    content = recorded['messages'][1]['content']
    assert content[2]['image_url']['url'].startswith('data:image/webp;base64,')
    assert recorded['response_format']['json_schema']['name'] == 'Draft'
    assert result.insufficient and usage['total_tokens'] == 17


def test_benchmark_gate_does_not_reward_blanket_refusals():
    from scripts.check_visual_accuracy import fixtures, apply_review
    images, cases = fixtures()
    for image in images:
        image.close()
    assert len(cases) == 40
    assert {kind: sum(c['category'] == kind for c in cases) for kind in ('pictures', 'diagrams', 'charts', 'tables')} == dict.fromkeys(('pictures', 'diagrams', 'charts', 'tables'), 10)
    report = {'checks': [{**case, 'visual': {'status': 'REFUSE'}} for case in cases]}
    reviews = {c['id']: dict(baseline_correct=False, visual_correct=True, citation_correct=True, invented_number=False) for c in cases}
    apply_review(report, reviews)
    assert report['release_gate'] == 'failed'
    assert report['answerable_accuracy'] == 0
