"""Provider smoke checks are validated with fake clients, without hosted requests."""
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

import test_gemma4 as smoke


@pytest.mark.parametrize('provider,expected_model', [('primary', 'primary-model'), ('fallback', 'fallback-model')])
def test_stream_uses_matching_provider_and_model(monkeypatch, capsys, provider, expected_model):
    monkeypatch.setattr(smoke.cfg, 'LLM_MODEL', 'primary-model')
    monkeypatch.setattr(smoke.cfg, 'FALLBACK_MODEL', 'fallback-model')
    monkeypatch.setattr(smoke.llm, 'has_valid_primary_key', lambda: True)
    monkeypatch.setattr(smoke.llm, 'has_valid_fallback_key', lambda: True)
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return nullcontext(iter([
            SimpleNamespace(choices=[]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None))]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='Hello!'))]),
        ]))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(smoke.llm, f'get_{provider}_client', lambda: nullcontext(client))
    other = 'fallback' if provider == 'primary' else 'primary'
    monkeypatch.setattr(smoke.llm, f'get_{other}_client', lambda: pytest.fail('Wrong provider selected'))
    smoke.run_smoke(provider, 'A test prompt')
    assert calls == [{'model': expected_model, 'messages': [{'role': 'user', 'content': 'A test prompt'}],
                      'max_tokens': 100, 'stream': True}]
    assert 'Hello!' in capsys.readouterr().out


@pytest.mark.parametrize('provider', ['primary', 'fallback'])
def test_missing_credentials_do_not_create_client(monkeypatch, provider):
    monkeypatch.setattr(smoke.llm, f'has_valid_{provider}_key', lambda: False)
    monkeypatch.setattr(smoke.llm, f'get_{provider}_client', lambda: pytest.fail('Unexpected API client'))
    with pytest.raises(ValueError, match='valid'):
        smoke.run_smoke(provider)


def test_cli_returns_failure_without_exposing_provider_error(monkeypatch, capsys):
    def fail(*args):
        raise RuntimeError('sensitive request details')
    monkeypatch.setattr(smoke, 'run_smoke', fail)
    assert smoke.main(['--provider', 'primary']) == 1
    error = capsys.readouterr().err
    assert 'primary' in error and 'RuntimeError' in error
    assert 'sensitive request details' not in error


def test_empty_stream_is_not_success(monkeypatch):
    monkeypatch.setattr(smoke.llm, 'has_valid_fallback_key', lambda: True)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kwargs: nullcontext(iter([])))))
    monkeypatch.setattr(smoke.llm, 'get_fallback_client', lambda: nullcontext(client))
    with pytest.raises(RuntimeError, match='no text'):
        smoke.run_smoke()
