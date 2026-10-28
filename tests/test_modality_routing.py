"""Unit tests for Modality-Aware Query Routing (RAG-Anything pattern).

Verifies cross-modal classification and dynamic retrieval boosting:
- Detects visual vs tabular vs textual user queries.
- Prevents text-centric retrieval bias by promoting visual/tabular evidence nodes.
"""
import numpy as np
import pytest

from app.query_intent import (
    detect_query_modality,
    MODALITY_VISUAL,
    MODALITY_TABULAR,
    MODALITY_TEXTUAL,
)
from app.retriever import HybridRetriever, is_visual_chunk, is_tabular_chunk


def test_detect_query_modality_visual():
    visual_queries = [
        "What does Figure 1 show?",
        "Show the architecture diagram",
        "What color is the arrow in Fig. 2?",
        "What does the network flowchart look like?",
        "Is there a plot of benchmark latency?",
        "Can you show visually how the components connect?",
        "What is depicted in the illustration?",
        "Show me the system blueprint and schematic",
    ]
    for q in visual_queries:
        assert detect_query_modality(q) == MODALITY_VISUAL, f"Failed on visual query: {q}"


def test_detect_query_modality_tabular():
    tabular_queries = [
        "What is the fee schedule in Table 2?",
        "Compare the columns in the pricing matrix",
        "What are the rows in the SLA uptime breakdown?",
        "What is in Table 3?",
        "Check the spreadsheet grid for Q3 revenue",
        "What are the table cells under tier 2?",
    ]
    for q in tabular_queries:
        assert detect_query_modality(q) == MODALITY_TABULAR, f"Failed on tabular query: {q}"


def test_detect_query_modality_textual():
    textual_queries = [
        "What is the termination clause in Section 4?",
        "Define mitochondria",
        "What is a cell?",  # Must NOT be confused with spreadsheet cell
        "Explain the privacy and security policy",
        "How are disputes resolved under this agreement?",
        "Who is responsible for server maintenance?",
    ]
    for q in textual_queries:
        assert detect_query_modality(q) == MODALITY_TEXTUAL, f"Failed on textual query: {q}"


def test_is_visual_and_tabular_chunk_predicates():
    vis_chunk = {
        "id": 1,
        "page": 1,
        "parent_text": "Overview of the neural engine",
        "child_text": "Overview of the neural engine",
        "has_visual": True,
        "image_url": "/static/crops/engine_vis.webp",
    }
    assert is_visual_chunk(vis_chunk)
    assert not is_tabular_chunk(vis_chunk)

    tbl_chunk = {
        "id": 2,
        "page": 2,
        "parent_text": "| Tier | Uptime | Credits |\n| Gold | 99.9% | 10% |",
        "child_text": "| Gold | 99.9% | 10% |",
        "visual_type": "table",
    }
    assert is_tabular_chunk(tbl_chunk)

    text_chunk = {
        "id": 3,
        "page": 3,
        "parent_text": "The provider guarantees high availability across all data centers.",
        "child_text": "The provider guarantees high availability across all data centers.",
    }
    assert not is_visual_chunk(text_chunk)
    assert not is_tabular_chunk(text_chunk)


def test_modality_routing_boosts_visual_nodes_above_text_nodes(monkeypatch):
    """
    RAG-Anything Principle: When a visual question is asked, visual evidence
    chunks must be promoted above pure text paragraphs that might otherwise dominate BM25.
    """
    import app.retriever as retriever_module

    # Mock embed_query to return a unit vector
    monkeypatch.setattr(retriever_module, "embed_query", lambda _: np.array([1.0, 0.0]))

    # Chunk 0: Pure text paragraph mentioning diagram terminology (slightly higher base text similarity)
    # Chunk 1: Visual node with an actual crop and linked visual
    chunks = [
        {
            "id": 0,
            "page": 1,
            "ast_node_id": "para_intro",
            "parent_text": "This section introduces the diagram terminology and conceptual architecture framework.",
            "child_text": "This section introduces the diagram terminology and conceptual architecture framework.",
            "has_visual": False,
        },
        {
            "id": 1,
            "page": 1,
            "ast_node_id": "vis_arch_fig",
            "parent_text": "Figure 1: High-level System Architecture Diagram displaying microservices and gateways.",
            "child_text": "Figure 1: High-level System Architecture Diagram displaying microservices and gateways.",
            "has_visual": True,
            "image_url": "/static/crops/fig1.webp",
            "linked_visuals": [{"id": "vis_1", "visual_type": "figure"}],
        },
    ]

    # Pre-computed unit vectors:
    # Chunk 0 has slightly higher dot product (0.95 vs 0.85) to simulate text-centric bias
    embeddings = np.array([
        [0.95, 0.05],
        [0.85, 0.15],
    ])

    retriever = HybridRetriever(chunks, embeddings)

    # 1. Textual Query: Pure text chunk wins because base scores are higher
    text_hits = retriever.retrieve("What is the conceptual architecture framework?", top_k=2)
    assert text_hits[0]["id"] == 0
    assert text_hits[0]["query_modality"] == MODALITY_TEXTUAL

    # 2. Visual Query: Visual node is boosted and outranks the text paragraph!
    visual_hits = retriever.retrieve("What does Figure 1 architecture diagram look like?", top_k=2)
    assert visual_hits[0]["id"] == 1
    assert visual_hits[0]["has_visual"] is True
    assert visual_hits[0]["query_modality"] == MODALITY_VISUAL


def test_modality_routing_boosts_tabular_nodes(monkeypatch):
    import app.retriever as retriever_module

    monkeypatch.setattr(retriever_module, "embed_query", lambda _: np.array([1.0, 0.0]))

    chunks = [
        {
            "id": 0,
            "page": 1,
            "ast_node_id": "para_sla_text",
            "parent_text": "Service uptime guarantees and penalties are detailed in our enterprise schedule.",
            "child_text": "Service uptime guarantees and penalties are detailed in our enterprise schedule.",
        },
        {
            "id": 1,
            "page": 1,
            "ast_node_id": "tbl_sla_matrix",
            "parent_text": "| Tier | Target | SLA |\n| Mission Critical | 99.99% | Tier 1 |",
            "child_text": "| Mission Critical | 99.99% | Tier 1 |",
            "visual_type": "table",
        },
    ]

    embeddings = np.array([
        [0.95, 0.05],
        [0.85, 0.15],
    ])

    retriever = HybridRetriever(chunks, embeddings)

    # When query specifically asks for table/matrix, tabular chunk is boosted
    hits = retriever.retrieve("Show the SLA uptime table matrix", top_k=2)
    assert hits[0]["id"] == 1
    assert hits[0]["query_modality"] == MODALITY_TABULAR



# ---------------------------------------------------------------------------
# Step 4: one shared visual-intent pattern for ranking AND the vision gate
# ---------------------------------------------------------------------------

def test_vision_gate_and_retriever_share_one_pattern():
    import app.vision as vision
    from app.query_intent import VISUAL_QUERY_PATTERN
    assert vision.VISUAL_QUERY is VISUAL_QUERY_PATTERN


@pytest.mark.parametrize("query", [
    "What is the response timeline?",
    "Describe the page layout requirements",
    "When is the court appearance scheduled?",
    "What are the visual inspection requirements?",
])
def test_prose_questions_never_reach_the_refusing_vision_gate(query):
    """The vision gate refuses when no image matches; prose questions must bypass it."""
    import app.vision as vision
    assert detect_query_modality(query) != MODALITY_VISUAL
    assert not vision.VISUAL_QUERY.search(query)
    # No AST/visuals and no visual intent -> falls through to the text path.
    assert vision.visual_answer(None, query, []) is None


@pytest.mark.parametrize("query", [
    "What is shown in Figure 2?",
    "What color is the circle?",
    "What does the flowchart depict?",
    "Explain the schematic",
])
def test_visual_questions_reach_vision_gate(query):
    import app.vision as vision
    assert detect_query_modality(query) == MODALITY_VISUAL
    assert vision.VISUAL_QUERY.search(query)
