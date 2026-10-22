"""Exact-text embedding reuse with bounded batches and stable output ordering."""
import hashlib
import logging
import sqlite3
from collections import OrderedDict
from threading import Lock, RLock
from typing import List

import numpy as np
from app.core.config import DEFAULT_EMBED_MODEL, INDEX_DIR

logger = logging.getLogger(__name__)
_embedding_model = None
_model_lock = Lock()
_cache_lock = RLock()
_memory_cache = OrderedDict()
EMBED_CACHE_PATH = INDEX_DIR / "embeddings.sqlite3"
EMBED_BATCH_SIZE = 64
EMBED_LRU_SIZE = 4096
_stats = {"hits": 0, "misses": 0, "model_calls": 0}


def get_embedding_model():
    """Load the configured FastEmbed model once; initialization is thread safe."""
    global _embedding_model
    with _model_lock:
        if _embedding_model is None:
            from fastembed import TextEmbedding
            _embedding_model = TextEmbedding(model_name=DEFAULT_EMBED_MODEL)
    return _embedding_model


def embedding_cache_stats():
    with _cache_lock:
        return dict(_stats)


def _key(text):
    # Identity normalization intentionally preserves case and whitespace: changing
    # either can change the model's tokens and therefore retrieval semantics.
    return hashlib.sha256((DEFAULT_EMBED_MODEL + "\0" + text).encode("utf-8")).hexdigest()


def _remember(key, vector):
    _memory_cache[key] = vector
    _memory_cache.move_to_end(key)
    while len(_memory_cache) > EMBED_LRU_SIZE:
        _memory_cache.popitem(last=False)


def _connect():
    EMBED_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(EMBED_CACHE_PATH), timeout=30)
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE IF NOT EXISTS embeddings (key TEXT PRIMARY KEY, dim INTEGER NOT NULL, vector BLOB NOT NULL, checksum TEXT NOT NULL)")
        return db
    except Exception:
        db.close()
        raise


def embed_texts(texts: List[str]) -> np.ndarray:
    """Dedupe, length-bucket, embed misses in batches, scatter, and L2-normalize."""
    if not texts:
        return np.zeros((0, 384), dtype=np.float32)
    # One lock also coalesces concurrent requests for identical missing text.
    with _cache_lock:
        db = None
        try:
            try:
                db = _connect()
            except (OSError, sqlite3.Error):
                logger.warning("Embedding disk cache unavailable; using memory cache", exc_info=True)
            resolved = {}
            missing = []
            for text in dict.fromkeys(texts):
                key = _key(text)
                memory_key = (str(EMBED_CACHE_PATH), key)
                vector = _memory_cache.get(memory_key)
                if vector is not None:
                    _memory_cache.move_to_end(memory_key)
                elif db is not None:
                    try:
                        row = db.execute("SELECT dim, vector, checksum FROM embeddings WHERE key=?", (key,)).fetchone()
                        if row and row[0] > 0 and len(row[1]) == row[0] * 4 and hashlib.sha256(row[1]).hexdigest() == row[2]:
                            candidate = np.frombuffer(row[1], dtype=np.float32).copy()
                            if np.isfinite(candidate).all() and np.linalg.norm(candidate) > 0:
                                vector = candidate
                    except (ValueError, TypeError, sqlite3.Error):
                        logger.warning("Ignoring unreadable embedding cache entry", exc_info=True)
                if vector is None:
                    missing.append(text)
                    _stats["misses"] += 1
                else:
                    resolved[text] = vector
                    _remember(memory_key, vector)
                    _stats["hits"] += 1
            missing.sort(key=len)
            if missing:
                model = get_embedding_model()
                for offset in range(0, len(missing), EMBED_BATCH_SIZE):
                    batch = missing[offset:offset + EMBED_BATCH_SIZE]
                    _stats["model_calls"] += 1
                    matrix = np.asarray(list(model.embed(batch, batch_size=EMBED_BATCH_SIZE)), dtype=np.float32)
                    if matrix.ndim != 2 or len(matrix) != len(batch) or not np.isfinite(matrix).all():
                        raise ValueError("Embedding model returned invalid vectors")
                    for text, vector in zip(batch, matrix):
                        key = _key(text)
                        resolved[text] = vector.copy()
                        _remember((str(EMBED_CACHE_PATH), key), resolved[text])
                        if db is not None:
                            raw = vector.tobytes()
                            try:
                                db.execute("INSERT OR REPLACE INTO embeddings VALUES (?, ?, ?, ?)",
                                           (key, len(vector), raw, hashlib.sha256(raw).hexdigest()))
                            except sqlite3.Error:
                                logger.warning("Could not persist embedding cache entry", exc_info=True)
                if db is not None:
                    try:
                        db.commit()
                    except sqlite3.Error:
                        logger.warning("Could not commit embedding cache", exc_info=True)
            matrix = np.stack([resolved[text] for text in texts]).astype(np.float32)
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            norms[norms == 0] = 1e-12
            return matrix / norms
        finally:
            if db is not None:
                db.close()


def embed_query(query: str) -> np.ndarray:
    return embed_texts([query])[0]
