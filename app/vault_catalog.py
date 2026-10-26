"""Durable catalog of attached documents; ingestion artifacts remain authoritative.

Only explicitly attached documents are cataloged. Benchmark/cache files are
never discovered automatically. SQLite transactions protect concurrent writes.
"""
import logging
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from app import config as cfg, indexing
from app.retriever import HybridRetriever

logger = logging.getLogger(__name__)

@contextmanager
def connection():
    path = indexing.CACHE_DIR.parent / 'vault.sqlite3'
    path.parent.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(path, timeout=15)
    try:
        database.execute('''CREATE TABLE IF NOT EXISTS documents (
            doc_id TEXT PRIMARY KEY, cache_key TEXT NOT NULL, filename TEXT NOT NULL,
            embedding_model TEXT NOT NULL, pipeline_version TEXT NOT NULL,
            uploaded_at TEXT NOT NULL)''')
        with database:
            yield database
    finally:
        database.close()


def remember_document(entry):
    key = entry.get('cache_key', '')
    if not re.fullmatch(r'[0-9a-f]{64}', key) or entry['doc_id'] != f'doc_{key[:32]}':
        raise ValueError('Document cache identity is invalid.')
    if not (indexing.CACHE_DIR / f'{key}.npz').is_file():
        raise ValueError('Ingestion cache is unavailable; this document cannot be restored yet.')
    with connection() as database:
        database.execute('''INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET cache_key=excluded.cache_key,
            filename=excluded.filename, embedding_model=excluded.embedding_model,
            pipeline_version=excluded.pipeline_version, uploaded_at=excluded.uploaded_at''',
            (entry['doc_id'], key, entry['filename'], cfg.DEFAULT_EMBED_MODEL,
             indexing.PIPELINE_VERSION, entry.get('uploaded_at') or datetime.now(timezone.utc).isoformat()))


def restore_documents():
    restored, unavailable = [], []
    with connection() as database:
        rows = database.execute('SELECT * FROM documents ORDER BY uploaded_at, doc_id').fetchall()
    for doc_id, key, filename, model, version, uploaded_at in rows:
        reason = None
        if not re.fullmatch(r'[0-9a-f]{64}', key) or doc_id != f'doc_{key[:32]}':
            reason = 'invalid_identity'
        elif model != cfg.DEFAULT_EMBED_MODEL or version != indexing.PIPELINE_VERSION:
            reason = 'configuration_changed'
        cached = None if reason else indexing._load_cache(key)
        if cached is None:
            unavailable.append({'doc_id': doc_id, 'filename': filename,
                                'reason': reason or 'cache_or_source_unavailable'})
            continue
        try:
            entry = _restore_entry(cached, doc_id, key, filename, uploaded_at)
        except Exception:
            logger.exception('Could not restore catalog document %s', doc_id)
            unavailable.append({'doc_id': doc_id, 'filename': filename,
                                'reason': 'invalid_cached_document'})
            continue
        restored.append(entry)
    return restored, unavailable


def _restore_entry(cached, doc_id, key, filename, uploaded_at):
    ast, chunks, classification, vectors, pages = cached
    ast.title = filename
    ast.nodes[ast.root_id].title = filename
    ast.nodes[ast.root_id].text = f'Document Root: {filename}'
    for chunk in chunks:
        chunk['filename'] = filename
    return {
        'doc_id': doc_id, 'cache_key': key, 'filename': filename, 'uploaded_at': uploaded_at,
        'ast': ast, 'chunks': chunks, 'retriever': HybridRetriever(chunks, vectors),
        'classification': classification, 'pages': pages, 'total_chunks': len(chunks),
        'total_ast_nodes': len(ast.nodes), 'cross_modal_links': len(ast.get_cross_modal_links()),
        'indexing_duration_ms': 0, 'stage_timings_ms': {}, 'cache_hit': True,
        'cache_warning': None, 'restored': True,
        'extraction': ast.nodes[ast.root_id].metadata.get('extraction', {}),
    }
