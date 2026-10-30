"""Durable catalog of attached documents; ingestion artifacts remain authoritative.

Only explicitly attached documents are cataloged. Benchmark/cache files are
never discovered automatically. SQLite transactions protect concurrent writes.
"""
import logging
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from app import auth, config as cfg, indexing
from app.retriever import HybridRetriever
from app.resource_limits import check_vault_capacity

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


def forget_document(doc_id, entry=None, vector_store=None):
    """Delete the catalog row and derived artifacts for one document.

    Returns True when anything was removed. Cache keys are account-scoped, so
    removing one user's cache never affects another user's identical upload.
    """
    if not re.fullmatch(r'doc_[0-9a-f]{32}', doc_id):
        return False
    with connection() as database:
        row = database.execute('SELECT cache_key FROM documents WHERE doc_id=?', (doc_id,)).fetchone()
        database.execute('DELETE FROM documents WHERE doc_id=?', (doc_id,))
    keys = {row[0]} if row else set()
    if entry and entry.get('cache_key'):
        keys.add(entry['cache_key'])
    removed = bool(row or entry)
    targets = [indexing.CACHE_DIR / f'{key}.npz' for key in keys if re.fullmatch(r'[0-9a-f]{64}', key)]
    targets.append(cfg.DOCS_DIR / f'{doc_id}.pdf')
    for folder in (cfg.PREVIEWS_DIR, cfg.CROPS_DIR):
        targets.extend(folder.glob(f'{doc_id}_*'))
    for target in targets:
        try:
            if target.is_file():
                target.unlink()
                removed = True
        except OSError:
            logger.warning('Could not delete %s for %s', target.name, doc_id)
    if vector_store is not None:
        try:
            removed = vector_store.drop_document(doc_id) or removed
        except Exception:
            logger.warning('Could not drop vector table for %s', doc_id)
    return removed


def restore_documents():
    restored, unavailable = [], []
    owned_filter = auth.all_owned_ids() if auth.enabled() else None
    with connection() as database:
        rows = database.execute('SELECT * FROM documents ORDER BY uploaded_at, doc_id').fetchall()
    for doc_id, key, filename, model, version, uploaded_at in rows:
        if owned_filter is not None and doc_id not in owned_filter:
            # Unowned legacy caches remain private and are not loaded in account mode.
            continue
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
            check_vault_capacity(restored, doc_id, len(cached[1]))
        except ValueError:
            unavailable.append({'doc_id': doc_id, 'filename': filename, 'reason': 'server_capacity'})
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
