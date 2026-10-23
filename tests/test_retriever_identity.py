"""Repeated text must not erase page-specific evidence or duplicate siblings."""
import numpy as np
import pytest

import app.retriever as retriever_module


@pytest.mark.parametrize("with_ids", [True, False])
def test_repeated_paragraphs_on_distinct_pages_keep_their_citations(monkeypatch, with_ids):
    chunks = []
    for page in (1, 100):
        for child in ("The service guarantees uptime.", "Credit is ten percent."):
            chunk = {"page": page, "filename": "manual.pdf", "child_text": child,
                     "parent_text": "The service guarantees uptime. Credit is ten percent.",
                     "image_url": f"/api/preview/doc/{page}"}
            if with_ids:
                chunk["ast_node_id"] = f"paragraph_{page}"
            chunks.append(chunk)
    vectors = np.array([[1.0, 0.0]] * len(chunks), dtype=np.float32)
    monkeypatch.setattr(retriever_module, "embed_query", lambda _: np.array([1.0, 0.0]))
    retriever = retriever_module.HybridRetriever(chunks, vectors)
    results = retriever.retrieve("uptime credit", top_k=4)
    assert len(results) == 2
    assert {result["page"] for result in results} == {1, 100}
    assert {result["citation_id"] for result in results} == {1, 2}
    assert all(result["image_url"].endswith(str(result["page"])) for result in results)


def test_distinct_parents_with_identical_text_on_same_page_remain_distinct(monkeypatch):
    chunks = [{"page": 5, "child_text": "Same clause.", "parent_text": "Same clause.",
               "ast_node_id": node_id} for node_id in ("paragraph_a", "paragraph_b")]
    monkeypatch.setattr(retriever_module, "embed_query", lambda _: np.array([1.0, 0.0]))
    retriever = retriever_module.HybridRetriever(chunks, np.array([[1.0, 0.0], [1.0, 0.0]]))
    assert len(retriever.retrieve("clause", top_k=4)) == 2
