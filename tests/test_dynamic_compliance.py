"""Unit & integration tests for dynamic compliance frameworks and custom checklists."""
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.audit_scanner import (
    AVAILABLE_FRAMEWORKS,
    DEFAULT_COMPLIANCE_CHECKS,
    FRAMEWORK_GDPR,
    FRAMEWORK_FINANCIAL,
    run_compliance_audit,
    verify_control_substance,
)
from app.ingest import extract_pages_from_text, hierarchical_chunk
from app.retriever import HybridRetriever
import app.main as main

client = TestClient(main.app)


def test_framework_catalog_structure():
    assert "sla" in AVAILABLE_FRAMEWORKS
    assert "gdpr" in AVAILABLE_FRAMEWORKS
    assert "financial" in AVAILABLE_FRAMEWORKS

    assert len(AVAILABLE_FRAMEWORKS["sla"]["checks"]) == 7
    assert len(AVAILABLE_FRAMEWORKS["gdpr"]["checks"]) == 6
    assert len(AVAILABLE_FRAMEWORKS["financial"]["checks"]) == 5

    for fw_key, fw in AVAILABLE_FRAMEWORKS.items():
        assert "name" in fw and len(fw["name"]) > 3
        assert "description" in fw
        assert "checks" in fw and len(fw["checks"]) > 0
        assert "playbook" in fw


def test_custom_compliance_checklist_execution(monkeypatch):
    import app.retriever as retriever_module

    sample_text = """Security Policies:
All customer records are encrypted at rest using AES-256 cryptographic ciphers across all storage volumes."""
    pages = extract_pages_from_text(sample_text, "security_sop.txt")
    chunks, _ = hierarchical_chunk(pages)
    embeddings = np.random.randn(len(chunks), 384).astype(np.float32)
    embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)

    # Mock embed_query so Chunk 0 matches with high similarity
    monkeypatch.setattr(retriever_module, "embed_query", lambda _: embeddings[0])

    retriever = HybridRetriever(chunks, embeddings)

    custom_checks = [
        {
            "id": "ENC-01",
            "category": "Data Protection",
            "title": "AES-256 Encryption at Rest",
            "query": "Is customer data encrypted at rest with AES-256?",
            "criticality": "CRITICAL",
            "required_terms": ["encrypted", "aes-256", "encryption", "ciphers"],
            "disqualifying_phrases": ["no encryption", "unencrypted"],
            "standard_clause": "Mandatory AES-256 storage volume encryption.",
            "action_required": "Enable storage volume encryption.",
        },
        {
            "id": "BAK-02",
            "category": "Resilience",
            "title": "Hourly Automated Snapshots",
            "query": "Are immutable database backups executed on an hourly schedule?",
            "criticality": "HIGH",
            "required_terms": ["snapshots", "hourly", "immutable", "backups"],
            "standard_clause": "Automated hourly immutable backup snapshotting.",
            "action_required": "Schedule hourly database snapshots.",
        },
    ]

    report = run_compliance_audit(retriever, checks=custom_checks)
    assert report["total_checks"] == 2
    assert report["passed_count"] == 1
    assert report["gaps_count"] == 1
    assert report["overall_score"] == 50.0
    assert report["verdict_color"] == "amber"

    # Verify pass item
    pass_item = next(c for c in report["checklist"] if c["id"] == "ENC-01")
    assert pass_item["status"] == "PASS"
    assert "AES-256" in pass_item["excerpt"] or "encrypted" in pass_item["excerpt"]

    # Verify gap item
    gap_item = next(c for c in report["checklist"] if c["id"] == "BAK-02")
    assert gap_item["status"] == "GAP"
    assert "Automated hourly" in gap_item["remediation_clause"]
    assert "+ " in gap_item["redline_diff"]


def test_custom_check_derives_terms_from_query_when_unspecified():
    check = {
        "id": "AUTO-01",
        "title": "Vendor Code Audit",
        "query": "Does the vendor undergo annual third-party penetration testing and source code audits?",
    }
    excerpt = "The vendor undergoes annual third-party penetration testing and independent code security audits."
    substance = verify_control_substance(excerpt, check)
    assert substance["substantive_pass"] is True
    assert len(substance["matched_terms"]) >= 2


def test_empty_custom_checks_does_not_divide_by_zero():
    retriever = HybridRetriever([], np.zeros((0, 384), dtype=np.float32))
    report = run_compliance_audit(retriever, checks=[])
    assert report["total_checks"] == 0
    assert report["overall_score"] == 100.0
    assert report["checklist"] == []


def test_api_list_frameworks_endpoint():
    res = client.get("/api/compliance/frameworks")
    assert res.status_code == 200
    data = res.json()
    assert "sla" in data
    assert "gdpr" in data
    assert "financial" in data
    assert data["sla"]["control_count"] == 7
    assert data["gdpr"]["control_count"] == 6
    assert data["financial"]["control_count"] == 5


def test_api_framework_selection_and_post_custom_audit():
    client.post("/load-sample")
    doc_id = main.ACTIVE_DOC_ID

    # 1. GET with framework=gdpr
    res_gdpr = client.get("/compliance-audit", params={"doc_id": doc_id, "framework": "gdpr"})
    assert res_gdpr.status_code == 200
    data_gdpr = res_gdpr.json()
    assert data_gdpr["framework"] == "gdpr"
    assert data_gdpr["total_checks"] == 6

    # 2. POST with custom checklist
    custom_payload = {
        "doc_id": doc_id,
        "framework": "custom",
        "custom_checks": [
            {
                "id": "SLA-CUSTOM",
                "title": "Custom Uptime Check",
                "query": "What is the guaranteed service availability or uptime percentage?",
                "required_terms": ["uptime", "availability", "99", "guarantee"],
            }
        ],
    }
    res_custom = client.post("/compliance-audit", json=custom_payload)
    assert res_custom.status_code == 200
    data_custom = res_custom.json()
    assert data_custom["framework"] == "custom"
    assert data_custom["total_checks"] == 1
    assert data_custom["checklist"][0]["id"] == "SLA-CUSTOM"
