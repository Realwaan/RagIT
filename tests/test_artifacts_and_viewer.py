import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

import app.main as main
from app.main import app, _hydrate_ast_siblings
from app.ast_builder import locate_pdf_text_bbox, DocumentAST, ASTNode, ASTNodeType
from app.artifacts_engine import (
    list_artifact_types,
    generate_executive_artifact,
    ArtifactType,
    ARTIFACT_METADATA
)

client = TestClient(app)
SAMPLE_PDF = Path("tests/fixtures/document_baseline_v1/native-1.pdf")


class MockRetriever:
    def __init__(self, chunks):
        self.chunks = chunks


# ---------------------------------------------------------------------------
# 1. Bounding Box Locator Tests
# ---------------------------------------------------------------------------

def test_locate_pdf_text_bbox_exact_and_bytes():
    assert SAMPLE_PDF.exists(), "Sample baseline PDF should exist"
    
    # Path input
    bbox_path = locate_pdf_text_bbox(SAMPLE_PDF, 1, "operational facts")
    assert bbox_path is not None
    assert len(bbox_path) == 4
    x0, y0, x1, y1 = bbox_path
    assert x0 < x1
    assert y0 < y1

    # Bytes input
    pdf_bytes = SAMPLE_PDF.read_bytes()
    bbox_bytes = locate_pdf_text_bbox(pdf_bytes, 1, "operational facts")
    assert bbox_bytes == bbox_path


def test_locate_pdf_text_bbox_edge_cases():
    # Page out of bounds
    assert locate_pdf_text_bbox(SAMPLE_PDF, 9999, "operational facts") is None
    # Page < 1
    assert locate_pdf_text_bbox(SAMPLE_PDF, 0, "operational facts") is None
    # Empty or missing snippet
    assert locate_pdf_text_bbox(SAMPLE_PDF, 1, "") is None
    # Non-existent phrase
    assert locate_pdf_text_bbox(SAMPLE_PDF, 1, "xyzNONEXISTENTphrase999") is None
    # Non-existent file path
    assert locate_pdf_text_bbox(Path("non_existent_file.pdf"), 1, "operational facts") is None


def test_hydrate_ast_siblings_populates_bbox_and_doc_id():
    ast = DocumentAST(doc_id="test_doc_bbox", title="Test Title")
    node = ASTNode(
        id="node_1",
        type=ASTNodeType.PARAGRAPH,
        title="Paragraph 1",
        text="Archive cover. This page contains no operational facts.",
        page=1,
        materialized_path="root/node_1"
    )
    ast.add_node(node)

    chunks = [
        {
            "id": "node_1",
            "type": "text",
            "text": "contains no operational facts",
            "page": 1,
            "filename": "native-1.pdf",
            "pdf_path": str(SAMPLE_PDF)
        }
    ]

    hydrated = _hydrate_ast_siblings(chunks, ast)
    assert len(hydrated) == 1
    chunk = hydrated[0]
    assert chunk["doc_id"] == "test_doc_bbox"
    assert "bbox" in chunk
    assert chunk["bbox"] is not None
    assert len(chunk["bbox"]) == 4


# ---------------------------------------------------------------------------
# 2. Artifacts Engine Catalog & Offline Generation Tests
# ---------------------------------------------------------------------------

def test_artifact_types_metadata_catalog():
    catalog = list_artifact_types()
    assert len(catalog) == 5
    type_ids = [item["id"] for item in catalog]
    expected_types = [
        "executive_briefing",
        "chronological_timeline",
        "study_guide_faq",
        "entity_risk_matrix",
        "audio_podcast_script"
    ]
    for exp in expected_types:
        assert exp in type_ids

    for meta in catalog:
        assert "title" in meta
        assert "description" in meta
        assert "icon" in meta


def test_generate_all_5_artifacts_offline_deterministic():
    sample_chunks = [
        {
            "id": "c1",
            "type": "text",
            "text": "On January 15, 2024, Acme Corp and Globex LLC executed this agreement. The baseline SLA requirement is 99.9% uptime with a $50,000 monthly service credit cap.",
            "parent_text": "On January 15, 2024, Acme Corp and Globex LLC executed this agreement. The baseline SLA requirement is 99.9% uptime with a $50,000 monthly service credit cap.",
            "page": 1,
            "filename": "msa_acme_globex.pdf",
            "bbox": [50.0, 700.0, 450.0, 750.0]
        },
        {
            "id": "c2",
            "type": "table",
            "text": "Table 1: 2024 Performance Metrics. In Q3 2024, measured uptime was 98.20%, incurring a liquidated penalty of $25,000.",
            "parent_text": "Table 1: 2024 Performance Metrics. In Q3 2024, measured uptime was 98.20%, incurring a liquidated penalty of $25,000.",
            "page": 2,
            "filename": "msa_acme_globex.pdf",
            "bbox": [60.0, 400.0, 460.0, 520.0]
        },
        {
            "id": "c3",
            "type": "text",
            "text": "Effective December 31, 2025, either party may terminate without cause upon 60 days advance written notice.",
            "parent_text": "Effective December 31, 2025, either party may terminate without cause upon 60 days advance written notice.",
            "page": 3,
            "filename": "msa_acme_globex.pdf",
            "bbox": [50.0, 300.0, 400.0, 340.0]
        }
    ]

    sample_doc_entry = {
        "doc_id": "doc_test_123",
        "filename": "msa_acme_globex.pdf",
        "retriever": MockRetriever(sample_chunks),
        "ast": None
    }

    artifact_types = [
        "executive_briefing",
        "chronological_timeline",
        "study_guide_faq",
        "entity_risk_matrix",
        "audio_podcast_script"
    ]

    with patch("app.artifacts_engine.has_valid_primary_key", return_value=False), \
         patch("app.artifacts_engine.has_valid_fallback_key", return_value=False):
        for art_type in artifact_types:
            res = generate_executive_artifact(sample_doc_entry, art_type)
            assert res["artifact_type"] == art_type
            assert res["doc_id"] == "doc_test_123"
            assert len(res["markdown"]) > 100
            assert len(res["sources"]) == 3
            assert res["generation_mode"] == "deterministic_offline"

            content = res["markdown"]
            # Verify markdown headings exist
            assert "#" in content
            # Verify citations are present
            assert "[1]" in content

            # Check type-specific content
            if art_type == "executive_briefing":
                assert "Executive Briefing" in content
                assert "Executive Summary" in content
                assert "Key Findings" in content
            elif art_type == "chronological_timeline":
                assert "Chronological" in content and "Timeline" in content
                assert "|" in content  # Contains Markdown table
                assert "2024" in content or "2025" in content
            elif art_type == "study_guide_faq":
                assert "Study Guide & Audit FAQ" in content
                assert "Terminology Glossary" in content
                assert "Frequently Asked Questions" in content
            elif art_type == "entity_risk_matrix":
                assert "Risk Matrix" in content
                assert "Obligation / Control" in content
                assert "Criticality" in content
            elif art_type == "audio_podcast_script":
                assert "Executive Audio Briefing Script" in content
                assert "**Alex:**" in content
                assert "**Jordan:**" in content


def test_generate_artifact_with_mock_llm():
    sample_chunks = [
        {
            "id": "c1",
            "type": "text",
            "text": "Vendor guarantees 99.99% availability.",
            "parent_text": "Vendor guarantees 99.99% availability.",
            "page": 1,
            "filename": "contract.pdf",
            "bbox": None
        }
    ]

    sample_doc_entry = {
        "doc_id": "doc_mock_llm",
        "filename": "contract.pdf",
        "retriever": MockRetriever(sample_chunks),
        "ast": None
    }

    mock_llm_response = (
        "# Executive Briefing: High Reliability\n\n"
        "Vendor guarantees enterprise uptime [1]. Recommended for mission-critical deployments."
    )

    with patch("app.artifacts_engine.has_valid_primary_key", return_value=True):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=mock_llm_response))]
        )
        with patch("app.artifacts_engine.get_primary_client", return_value=mock_client):
            res = generate_executive_artifact(sample_doc_entry, "executive_briefing")
            assert res["artifact_type"] == "executive_briefing"
            assert "Vendor guarantees enterprise uptime [1]" in res["markdown"]
            assert res["generation_mode"] == "llm_grounded"
            assert len(res["sources"]) == 1
            assert res["sources"][0]["citation_id"] == 1


# ---------------------------------------------------------------------------
# 3. FastApi Endpoints Integration Tests
# ---------------------------------------------------------------------------

def test_api_artifacts_types_endpoint():
    res = client.get("/api/artifacts/types")
    assert res.status_code == 200
    data = res.json()
    assert "types" in data
    assert len(data["types"]) == 5


def test_api_artifacts_generate_and_get():
    # 1. Load sample doc to ensure an active document exists
    load_res = client.post("/load-sample")
    assert load_res.status_code == 200
    doc_id = main.ACTIVE_DOC_ID
    assert doc_id, "ACTIVE_DOC_ID should be populated"

    # 2. Generate an executive briefing
    gen_res = client.post(
        "/api/artifacts/generate",
        json={
            "doc_id": doc_id,
            "artifact_type": "executive_briefing"
        }
    )
    assert gen_res.status_code == 200
    data = gen_res.json()
    assert data["artifact_type"] == "executive_briefing"
    assert data["doc_id"] == doc_id
    assert len(data["markdown"]) > 50
    assert len(data["sources"]) >= 1

    # Check that sources contain citations
    for s in data["sources"]:
        assert "citation_id" in s
        assert "page" in s
        assert "filename" in s

    # 3. Retrieve artifact via GET
    get_res = client.get(f"/api/artifacts/{doc_id}/executive_briefing")
    assert get_res.status_code == 200
    cached_data = get_res.json()
    assert cached_data["artifact_type"] == "executive_briefing"
    assert cached_data["markdown"] == data["markdown"]

    # 4. Unknown artifact type should return 400
    bad_res = client.post(
        "/api/artifacts/generate",
        json={
            "doc_id": doc_id,
            "artifact_type": "invalid_unknown_type"
        }
    )
    assert bad_res.status_code == 400

    bad_get_res = client.get(f"/api/artifacts/{doc_id}/invalid_unknown_type")
    assert bad_get_res.status_code == 400

    # 5. Omit doc_id in local mode defaults to ACTIVE_DOC_ID
    default_res = client.post(
        "/api/artifacts/generate",
        json={"artifact_type": "executive_briefing"}
    )
    assert default_res.status_code == 200
    assert default_res.json()["doc_id"] == doc_id

    # 6. Deleting document evicts cached artifact and returns 404 on subsequent GET
    del_res = client.delete(f"/vault/{doc_id}")
    assert del_res.status_code == 200
    missing_res = client.get(f"/api/artifacts/{doc_id}/executive_briefing")
    assert missing_res.status_code == 404
