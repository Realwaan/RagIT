import importlib
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
import app.main as main
from app.auditing.jobs import AuditJobManager
from tests.test_indexing_performance import isolated, TEXT


@pytest.mark.parametrize("package,names", [
    ("ingestion", "ingest ast_builder pdf_lock pdf_render indexing"),
    ("storage", "vector_store embeddings retriever"),
    ("auditing", "audit_scanner discrepancy_scanner classifier evaluator exporter"),
    ("core", "config llm generator"),
])
def test_compatibility_aliases_keep_module_identity(package, names, monkeypatch):
    for name in names.split():
        old = importlib.import_module(f"app.{name}")
        new = importlib.import_module(f"app.{package}.{name}")
        assert old is new
        monkeypatch.setattr(old, "_alias_probe", object(), raising=False)
        assert new._alias_probe is old._alias_probe


def test_audit_job_is_nonblocking_cached_and_does_not_switch_document(isolated, monkeypatch):
    import numpy as np
    import app.storage.retriever as retrieval
    monkeypatch.setattr(retrieval, "embed_query", lambda query: np.array([1.0] + [0.0] * 383, dtype=np.float32))
    monkeypatch.setattr(main, "generate_grounded_answer_with_telemetry",
                        lambda *args: ("The availability target is 99.9% [1].", {"total_tokens": 0}))
    entered, release = threading.Event(), threading.Event()
    calls = []
    def compliance(retriever):
        calls.append("compliance")
        entered.set()
        assert release.wait(10)
        return {"overall_score": 60}
    def discrepancies(ast, use_llm):
        calls.append("discrepancies")
        assert use_llm is False
        return {"verdict": "CONSISTENT"}
    manager = AuditJobManager(compliance, discrepancies)
    monkeypatch.setattr(main, "AUDIT_JOBS", manager)
    try:
        with TestClient(main.app) as client:
            doc_id = client.post("/upload", files={"file": ("first.txt", TEXT)}).json()["doc_id"]
            assert calls == []  # Upload must not trigger either audit.
            with ThreadPoolExecutor() as pool:
                response = pool.submit(client.post, "/api/jobs/audit", json={"doc_id": doc_id}).result(timeout=2)
            assert response.status_code == 202
            job_id = response.json()["job_id"]
            assert entered.wait(2)
            running = client.get(f"/api/jobs/{job_id}").json()
            assert running["status"] == "running" and running["progress"] == 10
            assert client.get("/health").status_code == 200
            with ThreadPoolExecutor() as pool:
                chat = pool.submit(client.post, "/ask", json={"query": "What is the uptime?"}).result(timeout=2)
            assert chat.status_code == 200 and "99.9%" in chat.json()["answer"]
            other = client.post("/upload", files={"file": ("other.txt", TEXT + b" A different policy applies.")}).json()["doc_id"]
            assert main.ACTIVE_DOC_ID == other
            release.set()
            manager.shutdown()
            done = client.get(f"/api/jobs/{job_id}").json()
            assert done["status"] == "completed" and done["progress"] == 100
            assert set(done["result"]) == {"compliance", "discrepancies"}
            assert main.ACTIVE_DOC_ID == other
            repeat = client.post("/api/jobs/audit", json={"doc_id": doc_id}).json()
            assert repeat["job_id"] == job_id and calls == ["compliance", "discrepancies"]
            assert client.get("/api/jobs/unknown").status_code == 404
            assert client.post("/api/jobs/audit", json={"doc_id": "unknown"}).status_code == 404
    finally:
        release.set()
        manager.shutdown()


def test_failed_audit_job_can_retry():
    attempts = []
    def audit(retriever):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("failed")
        return {}
    manager = AuditJobManager(audit, lambda *a, **k: {})
    failed = manager.submit("doc", None, None)
    manager.shutdown()
    assert manager.get(failed["job_id"])["status"] == "failed"
    retry = manager.submit("doc", None, None)
    manager.shutdown()
    assert retry["job_id"] != failed["job_id"]
    assert manager.get(retry["job_id"])["status"] == "completed"


def test_ragit_brand_and_existing_asset_routes():
    client = TestClient(main.app)
    assert "<title>RagIT</title>" in client.get("/").text
    assert "<title>RagIT" in client.get("/assistant").text
    assert "RagIT" in client.get("/openapi.json").json()["info"]["title"]
    script = client.get("/assets/index-Bi7Oxpxa.js")
    assert script.status_code == 200 and "RagIT" in script.text
    assert "AuditGuard" not in script.text
    assert client.get("/assets/index-BcYl17ML.css").status_code == 200
    primary_script = client.get("/static/app.js")
    assert primary_script.status_code == 200
    assert "auditguard_conversations_v2" in primary_script.text  # Preserve saved chats.
