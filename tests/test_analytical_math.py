"""
Unit and integration tests for Analytical Math Engine.
Verifies typed cell parsing, mathematical intent recognition, deterministic arithmetic execution,
step-by-step arithmetic proofs, LaTeX KaTeX formulas, and pipeline integration.
"""
import pytest
from app.analytical_math import (
    parse_typed_cell,
    parse_markdown_table_to_matrix,
    detect_math_intent,
    has_analytical_math_intent,
    format_number_output,
    execute_analytical_math,
    analytical_math_answer,
)
from app.generator import _build_extractive_fallback, build_grounded_prompt
from app.retriever import HybridRetriever
import numpy as np


TABLE_ORION = """
| Business | Revenue 2024 | Revenue 2025 |
| --- | --- | --- |
| Orion | 431 | 842 |
| Vega | 120 | 230 |
"""

TABLE_REGIONS = """
| Region | Sales 2024 | Profit 2024 |
| --- | --- | --- |
| North America | $500M | $120M |
| EMEA | $400M | $80M |
| APAC | $300M | $60M |
"""

TABLE_HIERARCHICAL = """
| Metric | Cost |
| --- | --- |
| Direct Costs | |
| Hardware | $500 |
| Software | $300 |
| Indirect Costs | |
| Hardware | $200 |
| Software | $100 |
"""


# -----------------------------------------------------------------------------
# 1. Typed Cell Parsing Tests
# -----------------------------------------------------------------------------

def test_parse_typed_cell_currencies_and_scales():
    c1 = parse_typed_cell("$12.5M")
    assert c1 is not None
    assert c1.num == 12_500_000.0
    assert c1.cur == "$"
    assert c1.suffix == "M"
    assert not c1.is_neg

    c2 = parse_typed_cell("€450K")
    assert c2 is not None
    assert c2.num == 450_000.0
    assert c2.cur == "€"
    assert c2.suffix == "K"

    c3 = parse_typed_cell("£3.2B")
    assert c3 is not None
    assert c3.num == 3_200_000_000.0
    assert c3.cur == "£"

    c4 = parse_typed_cell("USD 1,250.50")
    assert c4 is not None
    assert c4.num == 1250.50
    assert c4.cur == "USD"


def test_parse_typed_cell_accounting_negatives_and_percentages():
    # Accounting bracket: (100) or ($50M)
    c1 = parse_typed_cell("(100)")
    assert c1 is not None
    assert c1.num == -100.0
    assert c1.is_neg

    c2 = parse_typed_cell("($50M)")
    assert c2 is not None
    assert c2.num == -50_000_000.0
    assert c2.cur == "$"
    assert c2.is_neg

    # Percentage
    c3 = parse_typed_cell("24.5%")
    assert c3 is not None
    assert c3.num == 24.5
    assert c3.is_percent

    # Standard negative sign
    c4 = parse_typed_cell("-$15.2M")
    assert c4 is not None
    assert c4.num == -15_200_000.0
    assert c4.is_neg


def test_parse_typed_cell_invalid_and_corrupted():
    assert parse_typed_cell("") is None
    assert parse_typed_cell("N/A") is None
    assert parse_typed_cell("\ufffd450") is None
    assert parse_typed_cell("Unknown") is None


# -----------------------------------------------------------------------------
# 2. Math Intent Detection Tests
# -----------------------------------------------------------------------------

def test_detect_math_intent_operations():
    assert detect_math_intent("What is the total revenue?") == "SUM"
    assert detect_math_intent("Calculate the sum of sales across regions") == "SUM"
    assert detect_math_intent("What is the average profit in 2024?") == "AVERAGE"
    assert detect_math_intent("What is the difference between 2025 and 2024?") == "DIFFERENCE"
    assert detect_math_intent("What was the percentage growth from 2024 to 2025?") == "PERCENTAGE_CHANGE"
    assert detect_math_intent("What is the profit margin for North America?") == "MARGIN"
    assert detect_math_intent("Which region had the highest Sales?") == "MAX"
    assert detect_math_intent("Which region had the lowest Profit?") == "MIN"
    assert detect_math_intent("What is the total count of regions?") == "COUNT"


def test_non_math_queries_return_none():
    assert detect_math_intent("What is the retention period?") is None
    assert detect_math_intent("Who is the review owner?") is None
    assert detect_math_intent("Define the term protoplasm") is None
    assert not has_analytical_math_intent("What is the authorization code?")


# -----------------------------------------------------------------------------
# 3. Deterministic Arithmetic Execution Tests
# -----------------------------------------------------------------------------

def test_sum_across_columns_for_single_row():
    q = "What is the total revenue of Orion across 2024 and 2025?"
    res = analytical_math_answer(q, TABLE_ORION)
    assert res is not None
    assert res.operation == "SUM"
    assert res.result_value == 1273.0
    assert "Total Orion is 1,273." in res.summary
    assert "431 (Revenue 2024) + 842 (Revenue 2025) = 1,273" in res.proof
    assert r"$$\text{Total} = 431 + 842 = 1,273$$" in res.latex


def test_percentage_growth_from_start_to_end_year():
    q = "What is the percentage growth of Orion Revenue from 2024 to 2025?"
    res = analytical_math_answer(q, TABLE_ORION)
    assert res is not None
    assert res.operation == "PERCENTAGE_CHANGE"
    assert round(res.result_value, 2) == 95.36
    assert "+95.36%" in res.summary
    assert "((842 [Revenue 2025] - 431 [Revenue 2024]) / 431 [Revenue 2024]) * 100% = +95.36%" in res.proof
    assert r"\text{Growth}" in res.latex


def test_difference_between_years_with_explicit_ordering():
    q = "What is the difference in Orion Revenue between 2025 and 2024?"
    res = analytical_math_answer(q, TABLE_ORION)
    assert res is not None
    assert res.operation == "DIFFERENCE"
    assert res.result_value == 411.0
    assert "Difference between Revenue 2025 and Revenue 2024 is 411." in res.summary
    assert "842 (Revenue 2025) - 431 (Revenue 2024) = 411" in res.proof


def test_sum_across_rows_for_column():
    q = "What is the total Sales across all regions in 2024?"
    res = analytical_math_answer(q, TABLE_REGIONS)
    assert res is not None
    assert res.operation == "SUM"
    assert res.result_value == 1_200_000_000.0
    assert "$1,200M" in res.summary
    assert "$500M (North America) + $400M (EMEA) + $300M (APAC) = $1,200M" in res.proof


def test_average_across_rows():
    q = "What is the average Profit in 2024 across all regions?"
    res = analytical_math_answer(q, TABLE_REGIONS)
    assert res is not None
    assert res.operation == "AVERAGE"
    # (120M + 80M + 60M) / 3 = 86.67M
    assert round(res.result_value / 1e6, 2) == 86.67
    assert "$86.67M" in res.summary
    assert r"$$\text{Average}" in res.latex


def test_profit_margin_ratio():
    q = "What is the profit margin for North America?"
    res = analytical_math_answer(q, TABLE_REGIONS)
    assert res is not None
    assert res.operation == "MARGIN"
    # 120M / 500M = 24.0%
    assert round(res.result_value, 2) == 24.00
    assert "24.00%" in res.summary
    assert "($120M [Profit 2024] / $500M [Sales 2024]) * 100% = 24.00%" in res.proof


def test_max_and_min_lookup():
    q_max = "Which region had the highest Sales in 2024?"
    res_max = analytical_math_answer(q_max, TABLE_REGIONS)
    assert res_max is not None
    assert res_max.operation == "MAX"
    assert "North America" in res_max.summary
    assert "$500M" in res_max.summary

    q_min = "Which region had the lowest Profit in 2024?"
    res_min = analytical_math_answer(q_min, TABLE_REGIONS)
    assert res_min is not None
    assert res_min.operation == "MIN"
    assert "APAC" in res_min.summary
    assert "$60M" in res_min.summary


def test_hierarchical_group_sum():
    q = "What is the total Direct Costs?"
    res = analytical_math_answer(q, TABLE_HIERARCHICAL)
    assert res is not None
    assert res.operation == "SUM"
    # Hardware ($500) + Software ($300) = $800
    assert res.result_value == 800.0
    assert "$800" in res.summary


# -----------------------------------------------------------------------------
# 4. Pipeline Integration Tests
# -----------------------------------------------------------------------------

def test_extractive_fallback_returns_grounded_arithmetic_answer():
    chunks = [
        {"citation_id": 1, "parent_text": TABLE_ORION, "filename": "financials.pdf", "page": 3}
    ]
    query = "What is the total revenue of Orion across 2024 and 2025?"
    ans = _build_extractive_fallback(query, chunks)
    assert "Total Orion is 1,273." in ans
    assert "**Arithmetic Proof:**" in ans
    assert "[1]" in ans
    assert r"$$\text{Total} = 431 + 842 = 1,273$$" in ans


def test_extractive_fallback_reports_conflicting_calculations():
    table_alt = TABLE_ORION.replace("842", "999")
    chunks = [
        {"citation_id": 1, "parent_text": TABLE_ORION},
        {"citation_id": 2, "parent_text": table_alt},
    ]
    query = "What is the total revenue of Orion across 2024 and 2025?"
    ans = _build_extractive_fallback(query, chunks)
    assert "Different source tables yield different calculations" in ans
    assert "[1]" in ans
    assert "[2]" in ans


def test_prompt_builder_injects_verified_arithmetic_evidence():
    chunks = [
        {"citation_id": 1, "parent_text": TABLE_ORION, "filename": "report.pdf", "page": 1}
    ]
    query = "What is the percentage growth of Orion Revenue from 2024 to 2025?"
    prompt = build_grounded_prompt(query, chunks)
    assert "=== VERIFIED ARITHMETIC EVIDENCE (GROUND TRUTH) ===" in prompt
    assert "Operation: PERCENTAGE_CHANGE" in prompt
    assert "+95.36%" in prompt
    assert "Do NOT alter, approximate, or recalculate this arithmetic" in prompt


def test_retriever_promotes_tabular_chunk_for_analytical_math():
    chunks = [
        {"citation_id": 1, "parent_text": "The company engages in research and development across various sectors.", "page": 1},
        {"citation_id": 2, "parent_text": TABLE_ORION, "page": 2},
    ]
    # 384-dimensional synthetic embeddings matching FastEmbed BAAI/bge-small-en-v1.5
    dense_matrix = np.zeros((2, 384), dtype=np.float32)
    dense_matrix[0, 0] = 0.8
    dense_matrix[1, 0] = 0.2

    retriever = HybridRetriever(chunks, dense_matrix)
    query = "What is the total revenue of Orion across 2024 and 2025?"
    hits = retriever.retrieve(query, top_k=2)
    assert len(hits) > 0
    # Tabular chunk (page 2) promoted to rank 1 due to analytical math definition boost
    assert hits[0]["page"] == 2
