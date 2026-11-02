"""
Unit and Integration Tests for RagIT Enterprise Architecture Modules.
Verifies TaskQueue, Database (SQLite WAL), Storage, VectorStore, and Inference Client Pool
designed for concurrent multi-user environments (up to 30 active users).
"""

import asyncio
import os
import tempfile
import pytest
import numpy as np
from pathlib import Path

from app.queue import InMemoryTaskQueue, TaskStatus, TaskJob
from app.database import SQLiteDatabase, DocumentRecord, QueryAuditRecord
from app.storage import LocalStorage
from app.vector_store import LanceVectorStore, get_vector_store
from app.inference_client import InferenceClientPool


@pytest.mark.anyio
async def test_task_queue_lifecycle():
    queue = InMemoryTaskQueue(max_workers=2)

    async def sample_handler(job: TaskJob):
        await asyncio.sleep(0.01)
        return {"processed": True, "doc": job.payload.get("doc_id")}

    queue.register_handler("ingest", sample_handler)
    await queue.start()

    job = await queue.enqueue("ingest", {"doc_id": "test_doc_1"}, user_id="user_alice")
    assert job.status in (TaskStatus.PENDING, TaskStatus.RUNNING)

    # Wait briefly for worker to complete
    for _ in range(50):
        await asyncio.sleep(0.02)
        polled = await queue.get_job(job.job_id)
        if polled and polled.status == TaskStatus.COMPLETED:
            break

    polled = await queue.get_job(job.job_id)
    assert polled is not None
    assert polled.status == TaskStatus.COMPLETED
    assert polled.result == {"processed": True, "doc": "test_doc_1"}

    # Test listing and filtering
    jobs = await queue.list_jobs(user_id="user_alice")
    assert len(jobs) >= 1
    assert jobs[0].job_id == job.job_id

    await queue.stop()


def test_database_wal_and_document_persistence(tmp_path):
    db_file = tmp_path / "test_ragit.db"
    db = SQLiteDatabase(db_path=db_file)

    # Verify WAL mode is active
    conn = db._get_connection()
    mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    assert mode.lower() == "wal"

    # Save document record
    doc = DocumentRecord(
        doc_id="doc_test_100",
        filename="report.pdf",
        pages=12,
        sha256="abcdef123456",
        user_id="alice",
        tenant_id="tenant_eng",
    )
    db.save_document(doc)

    retrieved = db.get_document("doc_test_100", tenant_id="tenant_eng")
    assert retrieved is not None
    assert retrieved.filename == "report.pdf"
    assert retrieved.pages == 12

    # Verify tenant isolation
    isolated = db.get_document("doc_test_100", tenant_id="tenant_sales")
    assert isolated is None

    # Test query audit logging
    audit = QueryAuditRecord(
        query_id="q_1",
        query_text="What is the gross margin?",
        doc_id="doc_test_100",
        user_id="alice",
        tenant_id="tenant_eng",
        status="SUCCESS",
        total_ms=18.5,
        total_tokens=150,
        created_at=1700000000.0,
        evaluation_badge="GROUNDED",
    )
    db.log_query(audit)
    history = db.get_query_history(tenant_id="tenant_eng")
    assert len(history) == 1
    assert history[0].query_text == "What is the gross margin?"


def test_storage_atomic_writes_and_path_safety(tmp_path):
    storage = LocalStorage(root_dir=tmp_path)

    data = b"Hello, RagIT Enterprise Storage!"
    key = "docs/2026/sample.pdf"
    uri = storage.save(key, data)
    assert Path(uri).is_file()

    loaded = storage.load(key)
    assert loaded == data
    assert storage.exists(key)

    # Path traversal protection test
    with pytest.raises(ValueError, match="Path traversal detected"):
        storage.save("../evil.sh", b"malicious content")

    deleted = storage.delete(key)
    assert deleted is True
    assert not storage.exists(key)


def test_vector_store_abstraction(tmp_path):
    db_path = tmp_path / "lance_test"
    store = LanceVectorStore(db_path=db_path)
    assert store.is_ready() is True
    assert store.has_document("non_existent_doc") is False
    assert store.drop_document("non_existent_doc") is False


def test_inference_client_pool_concurrency():
    pool = InferenceClientPool(max_concurrency=2)
    telemetry = pool.get_telemetry()
    assert telemetry["max_concurrency"] == 2

    # Test single query embedding with throttle
    vec = pool.embed_query("Enterprise architectural scalability")
    assert isinstance(vec, np.ndarray)
    assert vec.ndim == 1
    assert len(vec) in (384, 768)

    # Test batch embedding
    batch = ["Document query number one", "Document query number two"]
    matrix = pool.embed_texts(batch)
    assert isinstance(matrix, np.ndarray)
    assert matrix.shape[0] == 2
    assert matrix.ndim == 2

    stats = pool.get_telemetry()
    assert stats["queries_embedded"] >= 1
    assert stats["embeddings_served"] >= 2
