"""Inference optimizations must preserve every chunk and its vector alignment."""
import numpy as np
import pytest

import app.config as config
import app.embeddings as embeddings


def test_duplicate_text_is_inferred_once_and_restored_in_original_order(monkeypatch):
    texts = ["A much longer paragraph.", "short", "A much longer paragraph.", "middle length"]
    calls = []

    def vector(text):
        return np.array([len(text), sum(map(ord, text)) % 31, 1], dtype=np.float32)

    class Model:
        def embed(self, values, batch_size):
            calls.append((list(values), batch_size))
            return [vector(text) for text in values]

    monkeypatch.setattr(embeddings, "get_embedding_model", lambda: Model())
    actual = embeddings.embed_texts(texts)
    expected = np.array([vector(text) for text in texts])
    expected /= np.linalg.norm(expected, axis=1, keepdims=True)
    np.testing.assert_allclose(actual, expected)
    assert calls == [(["short", "middle length", "A much longer paragraph."], embeddings.EMBEDDING_BATCH_SIZE)]
    assert actual.dtype == np.float32
    assert actual.shape == (4, 3)


def test_empty_input_does_not_load_model(monkeypatch):
    monkeypatch.setattr(embeddings, "get_embedding_model", lambda: pytest.fail("Empty input loaded model"))
    assert embeddings.embed_texts([]).shape == (0, 384)


@pytest.mark.parametrize("vectors", [[], [[1, 0]], [[float("nan"), 0], [1, 0]]])
def test_invalid_model_outputs_fail_before_caching(monkeypatch, vectors):
    class Model:
        def embed(self, values, batch_size):
            return vectors
    monkeypatch.setattr(embeddings, "get_embedding_model", lambda: Model())
    with pytest.raises(ValueError, match="invalid vectors"):
        embeddings.embed_texts(["first", "second"])


@pytest.mark.parametrize("value, expected", [("0", 1), ("-5", 1), ("9999", 32), ("bad", 4), ("8", 8)])
def test_resource_settings_are_bounded(monkeypatch, value, expected):
    monkeypatch.setenv("TEST_INFERENCE_LIMIT", value)
    assert config._bounded_int_env("TEST_INFERENCE_LIMIT", 4, 1, 32) == expected


def test_model_initialization_uses_configured_threads(monkeypatch):
    import fastembed
    calls = []
    monkeypatch.setattr(embeddings, "_embedding_model", None)
    monkeypatch.setattr(fastembed, "TextEmbedding", lambda **kwargs: calls.append(kwargs) or object())
    first = embeddings.get_embedding_model()
    assert embeddings.get_embedding_model() is first
    assert calls == [{"model_name": embeddings.DEFAULT_EMBED_MODEL, "threads": embeddings.EMBEDDING_THREADS}]


def test_token_windows_preserve_late_facts_and_leave_inference_tokenizer_unchanged(monkeypatch):
    from types import SimpleNamespace
    from tokenizers import Tokenizer, models, pre_tokenizers, processors

    words = [f"fact{i}" for i in range(100)]
    tokenizer = Tokenizer(models.WordLevel({"[UNK]": 0, "[CLS]": 1, "[SEP]": 2,
                                           **{word: i + 3 for i, word in enumerate(words)}}, unk_token="[UNK]"))
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    tokenizer.post_processor = processors.TemplateProcessing(single="[CLS] $A [SEP]",
                                                              special_tokens=[("[CLS]", 1), ("[SEP]", 2)])
    tokenizer.enable_truncation(max_length=24)
    original = tokenizer.to_str()
    model = SimpleNamespace(model=SimpleNamespace(tokenizer=tokenizer))
    monkeypatch.setattr(embeddings, "get_embedding_model", lambda: model)
    monkeypatch.setattr(embeddings, "_splitter_source", None)
    windows = embeddings.split_embedding_text(" ".join(words))
    assert len(windows) > 1
    assert set(" ".join(windows).split()) == set(words)
    assert "fact99" in windows[-1]
    check = Tokenizer.from_str(original)
    check.no_truncation()
    assert all(len(check.encode(window).ids) <= 24 for window in windows)
    assert all(set(a.split()) & set(b.split()) for a, b in zip(windows, windows[1:]))
    assert tokenizer.to_str() == original


def test_short_children_do_not_load_tokenizer_or_model(monkeypatch):
    monkeypatch.setattr(embeddings, "DEFAULT_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    monkeypatch.setattr(embeddings, "get_embedding_model", lambda: pytest.fail("Short text loaded model"))
    assert embeddings.split_embedding_text("Fee is $50.") == ["Fee is $50."]
    assert embeddings.split_embedding_text("") == []
