import io
import pytest
from fastapi.testclient import TestClient
from app.main import app
import app.main as main

client = TestClient(app)


def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["lancedb_ready"] is True
    assert "llm_configured" in data


def test_load_sample_and_ast_endpoints():
    # 1. Load sample document (uses unified pipeline without hardcoded AST overrides)
    res = client.post("/load-sample")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "total_ast_nodes" in data
    assert "indexing_duration_ms" in data
    assert data["total_ast_nodes"] >= 4
    assert data["cross_modal_links"] >= 1

    # 2. Query AST endpoint
    ast_res = client.get("/api/ast")
    assert ast_res.status_code == 200
    ast_data = ast_res.json()
    assert "total_nodes" in ast_data
    assert "nodes" in ast_data
    assert "cross_modal_links" in ast_data
    assert "cross_modal_links_count" in ast_data
    assert ast_data["cross_modal_links_count"] == len(ast_data["cross_modal_links"])

    # 3. Query Discrepancies endpoint (verifies Table 1 98.20% vs 99.9% SLA breach is automatically detected)
    disc_res = client.get("/api/discrepancies", params={"doc_id": main.ACTIVE_DOC_ID})
    assert disc_res.status_code == 200
    disc_data = disc_res.json()
    assert "consistency_score" in disc_data
    assert disc_data["verdict"] == "FLAGGED"
    assert disc_data["contradictions_count"] >= 1
    assert len(disc_data["findings"]) >= 1


def test_upload_custom_document_and_guardrails():
    # Reject unsupported file extension
    bad_ext = client.post(
        "/upload",
        files={"file": ("malware.exe", io.BytesIO(b"binary"), "application/octet-stream")}
    )
    assert bad_ext.status_code == 400

    # Reject empty file
    empty_res = client.post(
        "/upload",
        files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")}
    )
    assert empty_res.status_code == 400

    # Upload a custom contract with a table discrepancy
    custom_doc = """1. SERVICE AVAILABILITY
1.1 Uptime Commitment: Vendor guarantees 99.9% monthly uptime across all regions.
Table 1: Regional Uptime Log:
| Region | Target | Actual | Status |
| US-East | 99.9% | 97.50% | Breach |
"""
    up_res = client.post(
        "/upload",
        files={"file": ("custom_sla.txt", io.BytesIO(custom_doc.encode("utf-8")), "text/plain")}
    )
    assert up_res.status_code == 200
    up_data = up_res.json()
    assert up_data["ok"] is True
    assert up_data["cross_modal_links"] >= 1

    disc_res = client.get("/api/discrepancies", params={"doc_id": main.ACTIVE_DOC_ID})
    assert disc_res.status_code == 200
    assert disc_res.json()["verdict"] == "FLAGGED"


def test_vault_endpoint():
    res = client.get("/vault")
    assert res.status_code == 200
    data = res.json()
    assert "vault" in data
    assert "active_doc_id" in data


def test_compliance_audit_api_endpoint():
    client.post("/load-sample")
    res = client.get("/compliance-audit", params={"doc_id": main.ACTIVE_DOC_ID})
    assert res.status_code == 200
    data = res.json()
    assert "overall_score" in data
    assert "checklist" in data
    assert len(data["checklist"]) == 7
    assert data["remediation_playbook_available"] is True

    # Passing controls must include both 'clause_excerpt' and 'excerpt' for UI compatibility
    passes = [c for c in data["checklist"] if c["status"] == "PASS"]
    assert len(passes) >= 4
    assert passes[0]["excerpt"] != ""
    assert passes[0]["clause_excerpt"] == passes[0]["excerpt"]

    # Gaps must include redline diffs
    gaps = [c for c in data["checklist"] if c["status"] == "GAP"]
    assert len(gaps) > 0
    assert gaps[0]["redline_diff"] is not None
    assert "+ " in gaps[0]["redline_diff"]


def test_export_report_all_formats():
    payload = {
        "query": "What is the penalty credit?",
        "answer": "A 15% billing credit applies [1].\n\n| Metric | Claim | Actual |\n| --- | --- | --- |\n| Uptime | 99.9% | 98.2% |",
        "sources": [{"citation_id": 1, "filename": "sample.txt", "page": 1, "dense_score": 0.85, "parent_text": "15% billing credit"}],
        "classification": {"label": "Legal Agreement / SLA", "type": "LEGAL_CONTRACT"},
        "evaluation": {"badge": "🛡️ GROUNDED", "confidence": 85.0},
        "baseline": "Plain baseline text.",
        "format": "markdown"
    }
    md_res = client.post("/export-report", json=payload)
    assert md_res.status_code == 200
    assert "RagIT" in md_res.text
    assert "AuditGuard" not in md_res.text
    assert "15% billing credit" in md_res.text

    payload["format"] = "json"
    json_res = client.post("/export-report", json=payload)
    assert json_res.status_code == 200
    parsed = json_res.json()
    assert parsed["query"] == "What is the penalty credit?"
    assert len(parsed["sources"]) == 1

    payload["format"] = "pdf"
    pdf_res = client.post("/export-report", json=payload)
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content.startswith(b"%PDF-1.4")

    payload["format"] = "docx"
    docx_res = client.post("/export-report", json=payload)
    assert docx_res.status_code == 200
    assert "officedocument.wordprocessingml.document" in docx_res.headers["content-type"]
    assert docx_res.content.startswith(b"PK")

    payload["format"] = "csv"
    csv_res = client.post("/export-report", json=payload)
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    assert "What is the penalty credit?" in csv_res.text


def test_model_toggle_updates_health():
    initial_model = client.get("/health").json()["model"]
    toggle_res = client.post("/api/model/toggle")
    assert toggle_res.status_code == 200
    new_model = toggle_res.json()["model"]
    assert new_model != initial_model
    assert client.get("/health").json()["model"] == new_model
    # Toggle back
    client.post("/api/model/toggle")


def test_models_discovery_and_select_endpoints():
    initial = client.get("/api/models")
    assert initial.status_code == 200
    body = initial.json()
    assert "active_model" in body
    assert "models" in body
    assert any(m["id"] == "llama-3.3-70b-versatile" for m in body["models"])

    sel = client.post("/api/model/select", json={"model": "llama-3.3-70b-versatile"})
    assert sel.status_code == 200
    sel_data = sel.json()
    assert sel_data["ok"] is True
    assert sel_data["model"] == "llama-3.3-70b-versatile"
    assert sel_data["provider"] == "groq"
    assert client.get("/health").json()["model"] == "llama-3.3-70b-versatile"

    bad = client.post("/api/model/select", json={"model": "nonexistent-model-xyz"})
    assert bad.status_code == 400

    # Restore default model
    client.post("/api/model/select", json={"model": "llama-3.1-8b-instant"})


def test_ask_and_query_endpoints_benchmark_fields():
    client.post("/load-sample")
    res = client.post("/ask", json={"doc_id": main.ACTIVE_DOC_ID, "query": "What is the penalty credit if availability drops below 99.5%?", "include_baseline": False})
    assert res.status_code == 200
    data = res.json()
    assert "retrieval_ms" in data
    assert "total_ms" in data
    assert data["retrieval_ms"] >= 0
    assert data["total_ms"] >= data["retrieval_ms"]
    assert "status" in data
    assert "evaluation" in data
    assert "token_telemetry" in data
    assert "total_ast_nodes" in data["token_telemetry"]
    assert "cross_modal_links" in data["token_telemetry"]


def test_chat_stream_includes_token_telemetry():
    import json
    client.post("/load-sample")
    res = client.post(
        "/api/chat",
        json={"doc_id": main.ACTIVE_DOC_ID, "query": "What is the penalty credit if availability drops below 99.5%?"},
    )
    assert res.status_code == 200
    done_events = []
    for line in res.text.splitlines():
        if line.startswith("data: "):
            evt = json.loads(line[6:])
            if evt.get("type") == "done":
                done_events.append(evt)
    assert len(done_events) == 1
    done = done_events[0]
    assert "retrieval_ms" in done
    assert "total_ms" in done
    assert "token_telemetry" in done
    assert done["token_telemetry"]["total_tokens"] > 0
    assert done["token_telemetry"]["grounded_prompt_tokens"] > 0
    assert done["token_telemetry"]["grounded_completion_tokens"] > 0
    assert done["estimated_tokens"] == done["token_telemetry"]["total_tokens"]


def test_classic_ui_retired_and_redirects():
    # Starlette TestClient follows redirects by default; verify 307 when unredirected
    res_raw = client.get("/classic", follow_redirects=False)
    assert res_raw.status_code == 307
    assert res_raw.headers["location"] == "/"

    # When followed, user lands on the modern assistant interface
    res = client.get("/classic")
    assert res.status_code == 200
    html = res.text
    assert '<div id="root">' in html
    assert "RagIT" in html
    assert "/static/assistant/assets/" in html

    # Ensure legacy glassmorphism elements and overkill buttons are completely retired
    assert 'id="baseline-card"' not in html
    assert 'id="compare-toggle"' not in html
    assert 'id="btn-load-sample"' not in html
    assert 'id="btn-open-ast"' not in html
    assert 'id="btn-open-discrepancy"' not in html
    assert 'id="btn-run-audit"' not in html
    assert 'id="dynamic-island"' not in html
    assert 'id="left-sidebar"' not in html
    assert 'id="conversation-list"' not in html
    assert 'id="landing-hero"' not in html
    assert 'floating-sphere' not in html
    assert 'id="perf-telemetry-popover"' not in html
    assert 'id="btn-new-chat"' not in html
    assert 'id="delete-conv-dialog"' not in html
    assert 'id="visual-chart-container"' not in html


def test_max_upload_size_limit(monkeypatch):
    import app.config as cfg
    assert cfg.MAX_UPLOAD_SIZE_BYTES == 500 * 1024 * 1024

    # Verify rejection when exceeding size
    monkeypatch.setattr(cfg, "MAX_UPLOAD_SIZE_BYTES", 50)
    oversized = client.post(
        "/upload",
        files={"file": ("large.txt", io.BytesIO(b"A" * 100), "text/plain")}
    )
    assert oversized.status_code == 413
    assert "File exceeds maximum allowed size of 0 MB." in oversized.json()["detail"]
