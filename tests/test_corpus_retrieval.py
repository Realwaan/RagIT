import pytest
import numpy as np
from types import SimpleNamespace
from fastapi.testclient import TestClient

import app.main as main
from app.retriever import HybridRetriever, CorpusRetriever
from app.embeddings import embed_query


class DummyRetriever:
    def __init__(self, doc_id, filename, chunks):
        self.doc_id = doc_id
        self.filename = filename
        self.chunks = chunks

    def retrieve(self, query, top_k=4, k_rrf=60, modality=None):
        q_words = set(query.lower().split())
        results = []
        for i, c in enumerate(self.chunks):
            chunk = dict(c)
            chunk["citation_id"] = i + 1
            chunk["filename"] = self.filename
            chunk["doc_id"] = self.doc_id
            c_words = set(chunk["child_text"].lower().split()) | set(chunk["parent_text"].lower().split())
            matched = bool(q_words & c_words)
            chunk["dense_score"] = 0.85 if matched else 0.40
            chunk["bm25_score"] = 2.5 if matched else 0.1
            chunk["rrf_score"] = 0.03 if matched else 0.01
            results.append(chunk)
        results.sort(key=lambda x: x["dense_score"], reverse=True)
        return results[:top_k]

    def escalate_page_scan(self, query, candidate_pages=None, ast=None, min_threshold=0.50):
        if self.doc_id == "doc_escalate":
            return [{
                "citation_id": 1,
                "child_text": "Whole-Page Scan (Page 4): Escalated recovery text...",
                "parent_text": "Escalated recovery text from doc_escalate.",
                "filename": self.filename,
                "page": 4,
                "dense_score": 0.88,
                "bm25_score": 0.90,
                "rrf_score": 0.88,
                "escalated_from": "whole_page_scan",
            }]
        return []


def test_corpus_retriever_federated_search():
    doc1_chunks = [
        {"parent_text": "Alpha Corp revenue was $10M in Q1.", "child_text": "Alpha revenue $10M", "page": 1},
        {"parent_text": "Alpha Corp costs were $5M in Q1.", "child_text": "Alpha costs $5M", "page": 2},
    ]
    doc2_chunks = [
        {"parent_text": "Beta LLC revenue was $20M in Q1.", "child_text": "Beta revenue $20M", "page": 1},
        {"parent_text": "Beta LLC costs were $12M in Q1.", "child_text": "Beta costs $12M", "page": 3},
    ]

    doc_entries = {
        "doc_alpha": {
            "retriever": DummyRetriever("doc_alpha", "Alpha_Report.pdf", doc1_chunks),
            "filename": "Alpha_Report.pdf",
        },
        "doc_beta": {
            "retriever": DummyRetriever("doc_beta", "Beta_Report.pdf", doc2_chunks),
            "filename": "Beta_Report.pdf",
        },
    }

    corpus = CorpusRetriever(doc_entries)
    assert len(corpus.chunks) == 4
    assert any(c["doc_id"] == "doc_alpha" for c in corpus.chunks)
    assert any(c["doc_id"] == "doc_beta" for c in corpus.chunks)

    # Query for revenue: both documents have relevant chunks
    hits = corpus.retrieve("revenue", top_k=4)
    assert len(hits) == 4
    # The top 2 hits are the two revenue chunks with dense_score 0.85
    top2_filenames = {h["filename"] for h in hits[:2]}
    assert top2_filenames == {"Alpha_Report.pdf", "Beta_Report.pdf"}
    top2_doc_ids = {h["doc_id"] for h in hits[:2]}
    assert top2_doc_ids == {"doc_alpha", "doc_beta"}
    # Citation IDs must be sequential 1, 2, 3, 4
    assert [h["citation_id"] for h in hits] == [1, 2, 3, 4]


def test_corpus_retriever_deduplication():
    # If same document returns two child chunks belonging to identical parent, deduplicate parent
    doc_chunks = [
        {"parent_text": "Unified parent clause.", "child_text": "clause part 1", "page": 1},
        {"parent_text": "Unified parent clause.", "child_text": "clause part 2", "page": 1},
    ]
    doc_entries = {
        "doc_one": {
            "retriever": DummyRetriever("doc_one", "Document1.pdf", doc_chunks),
            "filename": "Document1.pdf",
        }
    }
    corpus = CorpusRetriever(doc_entries)
    hits = corpus.retrieve("clause", top_k=4)
    assert len(hits) == 1
    assert hits[0]["parent_text"] == "Unified parent clause."


def test_corpus_retriever_escalate_page_scan():
    doc_entries = {
        "doc_normal": {
            "retriever": DummyRetriever("doc_normal", "Normal.pdf", []),
            "filename": "Normal.pdf",
        },
        "doc_escalate": {
            "retriever": DummyRetriever("doc_escalate", "Escalate.pdf", []),
            "filename": "Escalate.pdf",
        },
    }
    corpus = CorpusRetriever(doc_entries)
    res = corpus.escalate_page_scan("recovery text", min_threshold=0.50)
    assert len(res) == 1
    assert res[0]["doc_id"] == "doc_escalate"
    assert res[0]["filename"] == "Escalate.pdf"
    assert res[0]["page"] == 4
    assert res[0]["escalated_from"] == "whole_page_scan"


def test_corpus_retriever_empty_handling():
    corpus = CorpusRetriever({})
    assert corpus.chunks == []
    assert corpus.retrieve("anything") == []
    assert corpus.escalate_page_scan("anything") == []


@pytest.fixture
def multi_doc_vault(monkeypatch):
    doc1_chunks = [
        {"parent_text": "The contract duration is 36 months.", "child_text": "duration 36 months", "page": 1, "filename": "contract.pdf", "doc_id": "doc_1"},
    ]
    doc2_chunks = [
        {"parent_text": "The termination notice period is 60 days.", "child_text": "termination notice 60 days", "page": 2, "filename": "policy.pdf", "doc_id": "doc_2"},
    ]

    r1 = DummyRetriever("doc_1", "contract.pdf", doc1_chunks)
    r2 = DummyRetriever("doc_2", "policy.pdf", doc2_chunks)

    vault = {
        "doc_1": {
            "doc_id": "doc_1",
            "filename": "contract.pdf",
            "pages": 1,
            "total_chunks": 1,
            "retriever": r1,
            "ast": SimpleNamespace(title="contract.pdf", doc_id="doc_1", nodes={}, get_cross_modal_links=lambda: []),
            "classification": {"label": "Contract", "type": "LEGAL_CONTRACT"},
            "uploaded_at": "2026-11-04T00:00:00Z",
            "chunks": doc1_chunks,
        },
        "doc_2": {
            "doc_id": "doc_2",
            "filename": "policy.pdf",
            "pages": 2,
            "total_chunks": 1,
            "retriever": r2,
            "ast": SimpleNamespace(title="policy.pdf", doc_id="doc_2", nodes={}, get_cross_modal_links=lambda: []),
            "classification": {"label": "Policy", "type": "GENERAL_DOC"},
            "uploaded_at": "2026-11-04T00:00:00Z",
            "chunks": doc2_chunks,
        },
    }

    monkeypatch.setattr(main, "DOCUMENT_VAULT", vault)
    monkeypatch.setattr(main, "ACTIVE_DOC_ID", "doc_1")
    monkeypatch.setattr(main, "DOCUMENT_ASTS", {k: v["ast"] for k, v in vault.items()})
    monkeypatch.setattr(main, "visual_answer", lambda *args: None)
    monkeypatch.setattr(
        main,
        "generate_grounded_answer_with_telemetry",
        lambda q, chunks, p: (
            f"Answer from {len(chunks)} sources. " + " ".join(f"[{c['citation_id']}]" for c in chunks),
            {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20, "generation_mode": "mock"},
        ),
    )
    return vault


def test_api_ask_corpus_all(multi_doc_vault):
    client = TestClient(main.app)
    res = client.post("/ask", json={"query": "What is the duration?", "doc_id": "all"})
    assert res.status_code == 200
    data = res.json()
    assert data["doc_id"] == "all"
    assert "Corpus" in data["classification"]["category"]
    assert len(data["sources"]) > 0
    # Source attribution verification
    source_docs = {s["doc_id"] for s in data["sources"]}
    assert "doc_1" in source_docs


def test_api_query_corpus_wildcard(multi_doc_vault):
    client = TestClient(main.app)
    res = client.post("/query", json={"query": "What is the termination notice?", "doc_id": "*"})
    assert res.status_code == 200
    data = res.json()
    assert data["doc_id"] == "all"
    assert len(data["sources"]) > 0
    source_docs = {s["doc_id"] for s in data["sources"]}
    assert "doc_2" in source_docs


def test_api_vault_shows_corpus_readiness(multi_doc_vault):
    client = TestClient(main.app)
    res = client.get("/vault")
    assert res.status_code == 200
    data = res.json()
    assert data["total_documents"] == 2
    assert data["can_query_all"] is True


def test_api_empty_vault_corpus_returns_404(monkeypatch):
    monkeypatch.setattr(main, "DOCUMENT_VAULT", {})
    client = TestClient(main.app)
    res = client.post("/ask", json={"query": "test", "doc_id": "all"})
    assert res.status_code == 404
    assert "No documents available" in res.json()["detail"]


def test_api_ask_stream_corpus(multi_doc_vault):
    client = TestClient(main.app)
    res = client.get("/ask-stream", params={"query": "What is the duration?", "doc_id": "all"})
    assert res.status_code == 200
    assert "Answer from" in res.text
    assert res.headers.get("X-Document-ID") == "all"


def test_api_chat_stream_corpus(multi_doc_vault, monkeypatch):
    monkeypatch.setattr(main, "stream_grounded_answer", lambda q, chunks, p, **kw: iter(["Grounded response [1]"]))
    client = TestClient(main.app)
    res = client.post("/api/chat", json={"query": "What is the duration?", "doc_id": "all"})
    assert res.status_code == 200
    lines = [l for l in res.text.split("\n") if l.startswith("data: ")]
    import json
    events = [json.loads(l[6:]) for l in lines]
    types = [e["type"] for e in events]
    assert "activity" in types
    assert "sources" in types
    assert "done" in types
    sources_ev = next(e for e in events if e["type"] == "sources")
    assert len(sources_ev["sources"]) > 0


def test_corpus_retrieval_auth_scoping(multi_doc_vault, monkeypatch):
    import app.auth as auth
    monkeypatch.setattr(auth, "enabled", lambda: True)
    # User owns ONLY doc_1, not doc_2
    monkeypatch.setattr(auth, "owned_ids", lambda: {"doc_1"})

    snapshot = main.document_snapshot("all")
    assert snapshot["doc_id"] == "all"
    assert "1 document" in snapshot["filename"]
    assert "doc_1" in snapshot["retriever"].doc_entries
    assert "doc_2" not in snapshot["retriever"].doc_entries

    # When user owns no documents in vault, raises 404
    monkeypatch.setattr(auth, "owned_ids", lambda: set())
    with pytest.raises(main.HTTPException) as exc:
        main.document_snapshot("all")
    assert exc.value.status_code == 404

