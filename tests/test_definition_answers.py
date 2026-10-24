"""Definition questions must retrieve explanatory evidence, not matching labels."""
import numpy as np
import pytest

import app.generator as generator
import app.retriever as retrieval
from app.query_intent import definition_excerpt


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
