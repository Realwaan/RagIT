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
