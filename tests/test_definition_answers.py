"""Definition questions must retrieve explanatory evidence, not matching labels."""
import numpy as np
import pytest

import app.generator as generator
import app.retriever as retrieval
from app.query_intent import definition_excerpt, function_excerpt


DEFINITION = 'The cell is the fundamental structural and functional unit of all living organisms.'


@pytest.mark.parametrize('query', ['what is the cell', 'What is a cell?', 'define cell', 'What are cells?'])
def test_definition_outranks_contents_and_specialized_caption(monkeypatch, query):
    texts = ['The Cell .', '1 THE CELL', 'Part of a parietal cell is at the right.', DEFINITION]
    chunks = [dict(child_text=text, parent_text=text, page=i + 1, ast_node_id=str(i))
              for i, text in enumerate(texts)]
    scores = np.array([.84, .78, .62, .71])
    vectors = np.column_stack((scores, np.sqrt(1 - scores ** 2)))
    monkeypatch.setattr(retrieval, 'embed_query', lambda _: np.array([1., 0.]))
    results = retrieval.HybridRetriever(chunks, vectors).retrieve(query, top_k=2)
    assert results[0]['page'] == 4
    assert results[0]['dense_score'] == pytest.approx(.71)
    assert generator._build_extractive_fallback(query, results) == DEFINITION + ' [1]'


def test_question_scaffolding_does_not_match_foreword(monkeypatch):
    chunks = [
        dict(child_text='What is it and what does it mean?', parent_text='Foreword', page=1),
        dict(child_text='Mitochondria provide energy.', parent_text='Mitochondria provide energy.', page=2),
    ]
    monkeypatch.setattr(retrieval, 'embed_query', lambda _: np.array([1., 0.]))
    results = retrieval.HybridRetriever(chunks, np.array([[.1, .99], [.7, .71]])).retrieve('What is mitochondria?')
    assert next(c for c in results if c['page'] == 1)['bm25_score'] == 0


@pytest.mark.parametrize('text', ['The Cell .', '1 THE CELL', 'A parietal cell is a specialized gastric cell.', 'The cell is at the right.'])
def test_definition_fallback_refuses_labels_and_different_subjects(text):
    answer = generator._build_extractive_fallback('What is a cell?', [{'parent_text': text}])
    assert answer == 'I cannot verify this information in the provided document excerpts.'


def test_definition_is_an_exact_source_sentence():
    text = 'Introductory discussion. ' + DEFINITION + ' Different cell types have different shapes.'
    assert definition_excerpt('What is a cell?', text) == DEFINITION
    assert definition_excerpt('What is a parietal cell?', text) == ''


def test_streaming_followup_keeps_current_question_for_offline_generation(monkeypatch):
    monkeypatch.setattr(generator, 'has_valid_primary_key', lambda: False)
    monkeypatch.setattr(generator, 'has_valid_fallback_key', lambda: False)
    chunks = [{'parent_text': DEFINITION, 'citation_id': 2}]
    answer = ''.join(generator.stream_grounded_answer('What is a cell?', chunks, previous_question='What is histology?'))
    assert answer == DEFINITION + ' [2]'


@pytest.mark.parametrize(('query', 'text', 'expected'), [
    ('What is histology?', '1.2 MICROSCOPES AND TECHNIQUES Histology is the study of tissues.', 'Histology is the study of tissues.'),
    ('What are mitochondria?', '12 The Cell 1.11FUNCTION OF MITOCHONDRIA Mitochondria are the most recognizable orga\x02nelle.', 'Mitochondria are the most recognizable organelle.'),
    ('What is epithelium?', '2.1 OVERVIEW Epithelium is one of the four basic tissues.', 'Epithelium is one of the four basic tissues.'),
    ('What is the nucleus?', 'The nucleus—the largest structure in the cell—contains genetic material.', 'The nucleus—the largest structure in the cell—contains genetic material.'),
    ('What is cytoplasm?', 'The components are the nucleus and the cytoplasm, a complex aqueous gel.', 'The components are the nucleus and the cytoplasm, a complex aqueous gel.'),
    ('What are the two components of protoplasm?', 'The two components of the pro\x02toplasm are the nucleus and cytoplasm.', 'The two components of the protoplasm are the nucleus and cytoplasm.'),
    ('What is the uptime guarantee?', 'The uptime guarantee is 99.9%.', 'The uptime guarantee is 99.9%.'),
])
def test_definition_layout_and_relational_questions(query, text, expected):
    assert definition_excerpt(query, text) == expected
    assert generator._build_extractive_fallback(query, [{'parent_text': text, 'citation_id': 3}]) == expected + ' [3]'


def test_full_corpus_lookup_recovers_definition_outside_candidate_window(monkeypatch):
    chunks = [dict(child_text='The Cell', parent_text='The Cell', page=i + 1) for i in range(80)]
    chunks.append(dict(child_text=DEFINITION, parent_text=DEFINITION, page=100))
    vectors = np.array([[.9, .1]] * 80 + [[.6, .8]])
    monkeypatch.setattr(retrieval, 'embed_query', lambda _: np.array([1., 0.]))
    hits = retrieval.HybridRetriever(chunks, vectors).retrieve('What is a cell?', top_k=4)
    assert hits[0]['page'] == 100
    assert hits[0]['dense_score'] == .6


def test_function_answer_uses_explicit_action_not_a_heading(monkeypatch):
    query = 'What is the function of mitochondria?'
    clause = 'Mitochondria (Mi), which supply energy, are in the cytoplasm.'
    heading = '1.11 Ultrastructure and Function of Mitochondria'
    chunks = [dict(child_text=heading, parent_text=heading, page=1),
              dict(child_text=clause, parent_text=clause, page=2)]
    monkeypatch.setattr(retrieval, 'embed_query', lambda _: np.array([1., 0.]))
    hits = retrieval.HybridRetriever(chunks, np.array([[.9, .1], [.65, .75]])).retrieve(query)
    assert hits[0]['page'] == 2
    assert generator._build_extractive_fallback(query, hits) == clause + ' [1]'
    assert function_excerpt(query, heading) == ''
    assert function_excerpt(query, 'Mitochondria do not supply energy in this experiment.') == ''
    assert function_excerpt(query, 'Mitochondria are organelles. Other structures supply energy.') == ''


SLIDE_DEFINITION = ('An abstract data type (ADT) is a set of objects together with a set of operations.')
SLIDE = ('Prepared by: A. Lecturer Abstract Data Types \u2022' + SLIDE_DEFINITION +
         ' \u2022Abstract data types are mathematical abstractions; the operations do not specify an implementation.')


@pytest.mark.parametrize('query', [
    'What are the Abstract Data Types?', 'What is an abstract data type?',
    'Define abstract data types', 'What is ADT?', 'What are ADTs?',
    'What is an abstract data type (ADT)?', 'What are abstract data types on PDF page 4?',
])
def test_slide_definitions_ignore_bullets_and_resolve_source_acronyms(query):
    assert definition_excerpt(query, SLIDE) == SLIDE_DEFINITION
    answer = generator._build_extractive_fallback(query, [{'parent_text': SLIDE, 'citation_id': 2}])
    assert SLIDE_DEFINITION + ' [2]' in answer
    assert 'Prepared by' not in answer


@pytest.mark.parametrize(('query', 'source', 'expected'), [
    ('What are interfaces?', 'Interfaces are contracts.', 'Interfaces are contracts.'),
    ('What is encapsulation?', 'ENCAPSULATION\nEncapsulation is the bundling of data\nand methods into one unit.',
     'Encapsulation is the bundling of data and methods into one unit.'),
    ('What is a queue?', 'Queue\nA queue is a collection that processes elements in arrival order.',
     'A queue is a collection that processes elements in arrival order.'),
    ('What is the uptime guarantee?', '2.1 Uptime Guarantee: The service provider guarantees 99.9% availability.',
     'Uptime Guarantee: The service provider guarantees 99.9% availability.'),
    ('What is CPU?', 'A central processing unit (CPU) is the component that executes instructions.',
     'A central processing unit (CPU) is the component that executes instructions.'),
])
def test_definitions_across_domains_and_pdf_layouts(query, source, expected):
    assert definition_excerpt(query, source) == expected


@pytest.mark.parametrize('source', [
    'Abstract Data Types', 'Abstract Data Types: Arrays',
    'A concrete data type is a set of implemented operations.',
    'Abstract data types are shown on the right.',
    'Abstract data types are not specified in this document.',
    'Abstract data types are the',
])
def test_slide_support_does_not_turn_labels_or_unrelated_text_into_definitions(source):
    assert definition_excerpt('What are abstract data types?', source) == ''


def test_unknown_acronym_is_not_guessed():
    assert definition_excerpt('What is CPU?', 'A central processing unit executes instructions.') == ''


@pytest.mark.parametrize(('query', 'source', 'expected'), [
    ('What is corporate social responsibility?',
     'Corporate Social Responsibility (CSR) in Technology Corporate Social Responsibility (CSR) represents a commitment to responsible operations.',
     'Corporate Social Responsibility (CSR) represents a commitment to responsible operations.'),
    ('What is a computer crime?',
     'Computer & Internet Crimes (Course Framework) A Computer Crime encompasses illegal acts involving computing.',
     'A Computer Crime encompasses illegal acts involving computing.'),
    ('What is ethical hacking?',
     'Ethical Hacking Methodologies (Course Framework) Ethical Hacking involves authorized testing.',
     'Ethical Hacking involves authorized testing.'),
])
def test_merged_title_case_headings_preserve_the_definition(query, source, expected):
    assert definition_excerpt(query, source) == expected


def test_title_case_modifiers_are_not_a_heading():
    assert definition_excerpt('What is a cell?', 'A Gastric Parietal Cell is a specialized cell.') == ''


@pytest.mark.parametrize(('query', 'source'), [
    ('What is cytoplasm?', 'The cytoplasm is packed with many organelles.'),
    ('What is cytoplasm?', 'The cytoplasm is replete with filaments.'),
    ('What is epithelium?', 'On the oral side, the epithelium is nonkeratinized stratified squamous.'),
    ('What is epithelium?', 'PSEUDOSTRATIFIED epithelium consists of more than one type of epithelial cell.'),
    ('What is epithelium?', 'Epithelium and Exocrine Glands 35 2.6STRUCTURE AND FUNCTION OF PSEUDOSTRATIFIED EPITHELIUM Pseudostratified epithelium consists of more than one type of epithelial cell.'),
])
def test_contextual_observations_do_not_outrank_general_definitions(query, source):
    assert definition_excerpt(query, source) == ''


def test_definition_split_across_children_is_ranked_from_parent(monkeypatch):
    chunks = [dict(child_text='Abstract Data Types', parent_text='Abstract Data Types', page=1),
              dict(child_text='objects together with a set of operations.', parent_text=SLIDE, page=4)]
    monkeypatch.setattr(retrieval, 'embed_query', lambda _: np.array([1., 0.]))
    hits = retrieval.HybridRetriever(chunks, np.array([[.9, .1], [.6, .8]])).retrieve('What are abstract data types?', top_k=1)
    assert hits[0]['page'] == 4
    assert hits[0]['dense_score'] == .6
    assert SLIDE_DEFINITION in generator._build_extractive_fallback('What are abstract data types?', hits)


@pytest.mark.parametrize('endpoint', ['/ask', '/api/chat'])
def test_slide_definition_survives_relevance_generation_and_verification(monkeypatch, endpoint):
    import json
    from fastapi.testclient import TestClient
    import app.main as main
    import app.vision as vision

    chunks = [dict(child_text='Abstract Data Types', parent_text='Abstract Data Types', page=1),
              dict(child_text=SLIDE_DEFINITION, parent_text=SLIDE, page=4)]
    monkeypatch.setattr(retrieval, 'embed_query', lambda _: np.array([1., 0.]))
    retriever = retrieval.HybridRetriever(chunks, np.array([[.9, .1], [.7, .7]]))
    monkeypatch.setattr(main, 'DOCUMENT_VAULT', {'doc_test': {'retriever': retriever, 'classification': {}}})
    monkeypatch.setattr(main, 'DOCUMENT_ASTS', {})
    monkeypatch.setattr(main, 'ACTIVE_DOC_ID', 'doc_test')
    monkeypatch.setattr(generator, 'has_valid_primary_key', lambda: False)
    monkeypatch.setattr(generator, 'has_valid_fallback_key', lambda: False)
    monkeypatch.setattr(vision, 'configured', lambda: False)
    response = TestClient(main.app).post(endpoint, json={
        'query': 'What are the Abstract Data Types', 'doc_id': 'doc_test', 'include_baseline': False,
    })
    assert response.status_code == 200
    if endpoint == '/ask':
        result = response.json()
    else:
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        result = next(event for event in events if event['type'] == 'done')
    assert result['status'] == 'SUCCESS'
    assert SLIDE_DEFINITION + ' [1]' in result['answer']
    assert result['sources'][0]['page'] == 4
    assert result['evaluation']['citation_verified']
