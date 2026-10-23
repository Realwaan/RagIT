import numpy as np
from threading import Lock
from typing import List
from app.config import DEFAULT_EMBED_MODEL, EMBEDDING_BATCH_SIZE, EMBEDDING_THREADS

_embedding_model = None
_model_lock = Lock()
_splitter_lock = Lock()
_splitter_source = None
_splitter_tokenizer = None
_splitter_limit = None

def get_embedding_model():
    """Lazily load FastEmbed ONNX model."""
    global _embedding_model
    with _model_lock:
        if _embedding_model is None:
            from fastembed import TextEmbedding
            _embedding_model = TextEmbedding(model_name=DEFAULT_EMBED_MODEL, threads=EMBEDDING_THREADS)
    return _embedding_model

def embed_texts(texts: List[str]) -> np.ndarray:
    """
    Generates dense embeddings for a list of strings and normalizes to unit length (L2 norm).
    Pre-normalization allows cosine similarity to be computed via pure dot product.
    """
    if not texts:
        return np.zeros((0, 384), dtype=np.float32)

    # Keep every original chunk/citation, but infer identical text only once.
    # Nearby lengths share a batch to reduce attention work on padding. Neither
    # optimization changes the text submitted to the model or truncates it.
    unique_texts = sorted(dict.fromkeys(texts), key=len)
    positions = {text: index for index, text in enumerate(unique_texts)}
    model = get_embedding_model()
    matrix = np.asarray(list(model.embed(unique_texts, batch_size=EMBEDDING_BATCH_SIZE)), dtype=np.float32)
    if matrix.ndim != 2 or len(matrix) != len(unique_texts) or not np.isfinite(matrix).all():
        raise ValueError("Embedding model returned invalid vectors or an unexpected row count.")
    
    # Normalize each vector so ||v|| = 1
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1e-12
    matrix /= norms
    return matrix[[positions[text] for text in texts]]

def embed_query(query: str) -> np.ndarray:
    """Embeds a single query string into a normalized 1D vector."""
    model = get_embedding_model()
    embedding = list(model.embed([query]))[0]
    vec = np.array(embedding, dtype=np.float32)
    norm = np.linalg.norm(vec)
    return vec / (norm if norm > 0 else 1e-12)


def split_embedding_text(text: str) -> List[str]:
    """Return overlapping source slices that fit the model's real token limit.

    A private tokenizer clone avoids changing truncation/padding on the model
    concurrently used by uploads, chat and the background indexer.
    """
    if not text:
        return []
    # These supported models have >=256 token contexts; UTF-8 byte count is a
    # conservative upper bound on their content tokens for short child units.
    if DEFAULT_EMBED_MODEL in {
        "sentence-transformers/all-MiniLM-L6-v2", "BAAI/bge-small-en-v1.5"
    } and len(text.encode("utf-8")) <= 200:
        return [text]

    global _splitter_source, _splitter_tokenizer, _splitter_limit
    model = get_embedding_model()
    with _splitter_lock:
        if _splitter_source is not model:
            from tokenizers import Tokenizer
            source = getattr(getattr(model, "model", model), "tokenizer", None)
            truncation = source.truncation if source is not None else None
            if not truncation or not truncation.get("max_length"):
                raise ValueError("Embedding tokenizer must expose its token limit to split long text safely.")
            tokenizer = Tokenizer.from_str(source.to_str())
            tokenizer.no_truncation()
            tokenizer.no_padding()
            _splitter_tokenizer = tokenizer
            _splitter_limit = int(truncation["max_length"])
            _splitter_source = model
        tokenizer, limit = _splitter_tokenizer, _splitter_limit

    if len(tokenizer.encode(text).ids) <= limit:
        return [text]
    offsets = tokenizer.encode(text, add_special_tokens=False).offsets
    # Leave room for boundary retokenization; verify every final source slice.
    capacity = max(1, limit - tokenizer.num_special_tokens_to_add(False) - 8)
    overlap = min(32, capacity // 4)
    windows = []
    start = 0
    while start < len(offsets):
        end = min(len(offsets), start + capacity)
        while True:
            window = text[offsets[start][0]:offsets[end - 1][1]]
            excess = len(tokenizer.encode(window).ids) - limit
            if excess <= 0:
                break
            if end <= start + 1:
                raise ValueError("A text unit cannot fit within the embedding tokenizer limit.")
            end = max(start + 1, end - excess)
        if window.strip():
            windows.append(window)
        if end == len(offsets):
            break
        start = max(start + 1, end - overlap)
    return windows or [text]
