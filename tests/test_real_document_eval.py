import os

import pytest

from scripts import real_document_eval as evaluation


def test_matching_requires_all_terms_and_word_boundaries():
    case = {'answerable': True, 'expected_terms': ['add', 'remove', 'size', 'contains']}
    assert evaluation.expected_match(case, 'Add, remove, size, contains.', False)
    assert not evaluation.expected_match(case, 'Add, remove, size.', False)
    assert not evaluation.expected_match(case, 'Adding, remove, size, contains.', False)
    assert not evaluation.expected_match(case, 'Add, remove, size, contains.', True)
    assert evaluation.expected_match({'answerable': False}, '', True)


def test_evaluation_restores_state_on_failure(monkeypatch):
    vault, asts = evaluation.main.DOCUMENT_VAULT, evaluation.main.DOCUMENT_ASTS
    monkeypatch.setenv('RAGIT_AUTH_MODE', 'clerk')
    def fail():
        assert os.environ['RAGIT_AUTH_MODE'] == 'local'
        assert evaluation.main.DOCUMENT_VAULT is not vault
        raise RuntimeError('missing source')
    monkeypatch.setattr(evaluation, '_run_evaluation', fail)
    with pytest.raises(RuntimeError, match='missing source'):
        evaluation.run_evaluation()
    assert evaluation.main.DOCUMENT_VAULT is vault
    assert evaluation.main.DOCUMENT_ASTS is asts
    assert os.environ['RAGIT_AUTH_MODE'] == 'clerk'


def test_evaluation_rejects_production(monkeypatch):
    monkeypatch.setenv('RAGIT_ENV', 'production')
    with pytest.raises(ValueError, match='development'):
        evaluation.run_evaluation()
