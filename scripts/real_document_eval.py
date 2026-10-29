"""Run and review an evaluation benchmark on real, independently authored PDF documents.

Covers native PDFs, OCR/visual slide regions, structured tables, paraphrases, and unanswerable queries
across three real documents:
1. Netter's Essential Histology (2nd ed., Ovalle & Nahirney, 538 pages)
2. Lesson 8: SDG 8 Decent Work and Economic Growth (22 pages, mixed native text, OCR diagrams, and tables)
3. CSIT221 Topic 01: Data Abstraction and Array Review (CIT-University, 6 pages)
"""
import hashlib
import json
import math
import os
import platform
import re
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

import app.config as cfg
import app.main as main
from app.indexing import _load_cache
from app.vault_catalog import _restore_entry

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "reports" / "real-document-evaluation.json"

REAL_DOCUMENTS = [
    {
        "doc_id": "doc_fca54d18c79dcb2a891e57ef4cd72d41",
        "cache_key": "fca54d18c79dcb2a891e57ef4cd72d41b4e4959b646aeb3b0ecd1877ff7ecb2c",
        "filename": "Netter's Essential Histology (2nd ed.).pdf",
        "pages": 538,
        "provenance": "Independently authored medical textbook (Ovalle & Nahirney, ISBN 978-1455706310)",
    },
    {
        "doc_id": "doc_27a50b7d3c653d13548d50a126a052c6",
        "cache_key": "27a50b7d3c653d13548d50a126a052c6b47084161232c6f48078a0152d212c52",
        "filename": "Lesson8_SDG_8_Decent_Work_and_Economic_Growth.pdf",
        "pages": 22,
        "provenance": "Independently authored university lecture deck with native text, OCR slide graphics, and agency tables",
    },
    {
        "doc_id": "doc_e2576cf21cfbbec406c4e203f10be71d",
        "cache_key": "e2576cf21cfbbec406c4e203f10be71d7ecdbb9fd12c5a64748f783358297a99",
        "filename": "01_Data_Abstraction_and_Array_Review.pdf",
        "pages": 6,
        "provenance": "Independently authored CSIT221 lecture slides (College of Computer Studies, CIT-University)",
    },
]

FROZEN_CASES = [
    # Native PDF queries
    {
        "id": "real-native-1",
        "doc_id": "doc_fca54d18c79dcb2a891e57ef4cd72d41",
        "category": "native",
        "query": "What is histology?",
        "expected_substring": "visual science",
        "supporting_pages": [9],
        "answerable": True,
    },
    {
        "id": "real-native-2",
        "doc_id": "doc_fca54d18c79dcb2a891e57ef4cd72d41",
        "category": "native",
        "query": "What is a eukaryotic cell?",
        "expected_substring": "mass of protoplasm",
        "supporting_pages": [20],
        "answerable": True,
    },
    {
        "id": "real-native-3",
        "doc_id": "doc_fca54d18c79dcb2a891e57ef4cd72d41",
        "category": "native",
        "query": "What is epithelium?",
        "expected_substring": "four basic tissues",
        "supporting_pages": [48],
        "answerable": True,
    },
    {
        "id": "real-native-4",
        "doc_id": "doc_e2576cf21cfbbec406c4e203f10be71d",
        "category": "native",
        "query": "What is an abstract data type (ADT)?",
        "expected_substring": "set of objects together with a set of operations",
        "supporting_pages": [4],
        "answerable": True,
    },
    # Paraphrase queries
    {
        "id": "real-paraphrase-1",
        "doc_id": "doc_fca54d18c79dcb2a891e57ef4cd72d41",
        "category": "paraphrase",
        "query": "What are the two main parts that make up protoplasm?",
        "expected_substring": "nucleus",
        "supporting_pages": [20],
        "answerable": True,
    },
    {
        "id": "real-paraphrase-2",
        "doc_id": "doc_27a50b7d3c653d13548d50a126a052c6",
        "category": "paraphrase",
        "query": "What annual GDP growth rate is targeted for least developed countries under Target 8.1?",
        "expected_substring": "7%",
        "supporting_pages": [5],
        "answerable": True,
    },
    {
        "id": "real-paraphrase-3",
        "doc_id": "doc_e2576cf21cfbbec406c4e203f10be71d",
        "category": "paraphrase",
        "query": "What does abstraction mean in Object Oriented Programming?",
        "expected_substring": "without knowing how it works internally",
        "supporting_pages": [3],
        "answerable": True,
    },
    # Scanned / OCR region queries
    {
        "id": "real-scanned-1",
        "doc_id": "doc_27a50b7d3c653d13548d50a126a052c6",
        "category": "scanned",
        "query": "How many employees do micro, small, and medium enterprises (MSMEs) have by category?",
        "expected_substring": "1-9",
        "supporting_pages": [10],
        "answerable": True,
    },
    {
        "id": "real-scanned-2",
        "doc_id": "doc_27a50b7d3c653d13548d50a126a052c6",
        "category": "scanned",
        "query": "How do Targets 8.9 and 8.10 support inclusive economic participation?",
        "expected_substring": "sustainable tourism",
        "supporting_pages": [20],
        "answerable": True,
    },
    # Table queries
    {
        "id": "real-tables-1",
        "doc_id": "doc_27a50b7d3c653d13548d50a126a052c6",
        "category": "tables",
        "query": "What is the main role of DOLE in the agency table?",
        "expected_substring": "child labor prevention",
        "supporting_pages": [17],
        "answerable": True,
    },
    {
        "id": "real-tables-2",
        "doc_id": "doc_27a50b7d3c653d13548d50a126a052c6",
        "category": "tables",
        "query": "What is the main role of the Department of Justice (DOJ)?",
        "expected_substring": "prosecution",
        "supporting_pages": [17],
        "answerable": True,
    },
    # Visual / diagram context queries
    {
        "id": "real-visual-1",
        "doc_id": "doc_fca54d18c79dcb2a891e57ef4cd72d41",
        "category": "visual",
        "query": "Where are mitochondria located in the nerve cell and muscle cell comparison?",
        "expected_substring": "cytoplasm",
        "supporting_pages": [41],
        "answerable": True,
    },
    {
        "id": "real-visual-2",
        "doc_id": "doc_27a50b7d3c653d13548d50a126a052c6",
        "category": "visual",
        "query": "What is the productivity formula shown on page 9?",
        "expected_substring": "Total Output",
        "supporting_pages": [9],
        "answerable": True,
    },
    # Unanswerable queries (must refuse)
    {
        "id": "real-unanswerable-1",
        "doc_id": "doc_fca54d18c79dcb2a891e57ef4cd72d41",
        "category": "unanswerable",
        "query": "What is the tuition fee for the university medical program?",
        "expected_substring": None,
        "supporting_pages": [],
        "answerable": False,
    },
    {
        "id": "real-unanswerable-2",
        "doc_id": "doc_27a50b7d3c653d13548d50a126a052c6",
        "category": "unanswerable",
        "query": "What was the exact national unemployment percentage in 2024?",
        "expected_substring": None,
        "supporting_pages": [],
        "answerable": False,
    },
    {
        "id": "real-unanswerable-3",
        "doc_id": "doc_e2576cf21cfbbec406c4e203f10be71d",
        "category": "unanswerable",
        "query": "When is the final exam scheduled for CSIT221?",
        "expected_substring": None,
        "supporting_pages": [],
        "answerable": False,
    },
]


def run_evaluation():
    os.environ["RAGIT_AUTH_MODE"] = "local"
    entries = {}
    for doc in REAL_DOCUMENTS:
        cached = _load_cache(doc["cache_key"])
        if cached is None:
            raise RuntimeError(f"Missing real-document cache for {doc['doc_id']}")
        entry = _restore_entry(cached, doc["doc_id"], doc["cache_key"], doc["filename"], "2026-10-29T00:00:00Z")
        entries[doc["doc_id"]] = entry
        main.DOCUMENT_VAULT[doc["doc_id"]] = entry
        main.DOCUMENT_ASTS[doc["doc_id"]] = entry["ast"]

    client = TestClient(main.app)
    results = []
    with (
        patch("app.generator.has_valid_primary_key", return_value=False),
        patch("app.generator.has_valid_fallback_key", return_value=False),
        patch("app.vision.configured", return_value=False),
    ):
        for case in FROZEN_CASES:
            entry = entries[case["doc_id"]]
            hits = entry["retriever"].retrieve(case["query"], top_k=10)
            hit_pages = [h.get("page") for h in hits]
            expected_pages = set(case["supporting_pages"])
            retrieval_hit = bool(expected_pages & set(hit_pages)) if expected_pages else True

            t0 = time.perf_counter()
            res = client.post("/ask", json={"doc_id": case["doc_id"], "query": case["query"], "include_baseline": False})
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            res.raise_for_status()
            payload = res.json()

            answer = payload.get("answer", "")
            refused = payload.get("status") == "REFUSE"
            cited_ids = {int(x) for x in re.findall(r"\[(\d+)\]", answer)}
            cited_pages = sorted({s.get("page") for s in payload.get("sources", []) if s.get("citation_id") in cited_ids and s.get("page") is not None})

            if case["answerable"]:
                answer_match = (not refused) and (case["expected_substring"].casefold() in answer.casefold())
                citation_match = bool(expected_pages & set(cited_pages))
                if not retrieval_hit:
                    failure_type = "retrieval_failure"
                elif refused:
                    failure_type = "unnecessary_refusal"
                elif not answer_match:
                    failure_type = "unsupported_or_incomplete_answer"
                elif not citation_match:
                    failure_type = "citation_mismatch"
                else:
                    failure_type = None
            else:
                answer_match = refused
                citation_match = refused and len(cited_pages) == 0
                failure_type = None if refused else "unsupported_hallucination_on_unanswerable"

            results.append({
                **case,
                "answer": answer,
                "refused": refused,
                "retrieval_top10_pages": hit_pages,
                "retrieval_recall_at_10": 1.0 if retrieval_hit else 0.0,
                "cited_pages": cited_pages,
                "answer_correct": answer_match,
                "citation_correct": citation_match,
                "failure_taxonomy": failure_type,
                "latency_ms": latency_ms,
                "generation_mode": payload.get("generation_mode"),
                "tokens": payload.get("estimated_tokens", 0),
                "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
            })

    answerable_rows = [r for r in results if r["answerable"]]
    unanswerable_rows = [r for r in results if not r["answerable"]]
    latencies = sorted(r["latency_ms"] for r in results)

    summary = {
        "total_cases": len(results),
        "answerable_cases": len(answerable_rows),
        "unanswerable_cases": len(unanswerable_rows),
        "retrieval_recall_at_10": round(sum(r["retrieval_recall_at_10"] for r in answerable_rows) / len(answerable_rows), 4),
        "answer_accuracy": round(sum(r["answer_correct"] for r in results) / len(results), 4),
        "citation_accuracy_on_answerable": round(sum(r["citation_correct"] for r in answerable_rows) / len(answerable_rows), 4),
        "false_refusal_rate": round(sum(r["refused"] for r in answerable_rows) / len(answerable_rows), 4),
        "unanswerable_refusal_rate": round(sum(r["refused"] for r in unanswerable_rows) / len(unanswerable_rows), 4),
        "failure_breakdown": {
            "retrieval_failure": sum(r["failure_taxonomy"] == "retrieval_failure" for r in results),
            "extraction_failure": sum(r["failure_taxonomy"] == "extraction_failure" for r in results),
            "unsupported_or_incomplete_answer": sum(r["failure_taxonomy"] == "unsupported_or_incomplete_answer" for r in results),
            "unnecessary_refusal": sum(r["failure_taxonomy"] == "unnecessary_refusal" for r in results),
            "citation_mismatch": sum(r["failure_taxonomy"] == "citation_mismatch" for r in results),
            "unsupported_hallucination_on_unanswerable": sum(r["failure_taxonomy"] == "unsupported_hallucination_on_unanswerable" for r in results),
        },
        "latency_p50_ms": latencies[len(latencies) // 2],
        "latency_p95_ms": latencies[math.ceil(0.95 * len(latencies)) - 1],
        "total_tokens": sum(r["tokens"] for r in results),
    }

    by_category = {}
    for cat in sorted({r["category"] for r in results}):
        sub = [r for r in results if r["category"] == cat]
        by_category[cat] = {
            "count": len(sub),
            "answer_accuracy": round(sum(r["answer_correct"] for r in sub) / len(sub), 4),
            "citation_accuracy": round(sum(r["citation_correct"] for r in sub) / len(sub), 4),
            "false_refusals": sum(r["refused"] and r["answerable"] for r in sub),
        }

    report = {
        "evaluation_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime": {
            "python": platform.python_version(),
            "embedding_model": cfg.DEFAULT_EMBED_MODEL,
            "similarity_threshold": cfg.SIMILARITY_THRESHOLD,
            "top_k": cfg.TOP_K,
        },
        "scope_and_limitations": (
            "Evaluated on 3 independently authored real-world PDFs (566 total pages across a medical textbook, "
            "an SDG economics slide deck with OCR/tables, and a university CS lecture deck). "
            "Covers native text, paraphrases, OCR slide graphics, structured tables, visual captions, and unanswerable queries. "
            "Limitation: 16 curated real-document queries provide a verified smoke/audit benchmark with human-reviewed citations, "
            "not a large-scale statistical certification across arbitrary enterprise domains."
        ),
        "documents": REAL_DOCUMENTS,
        "summary": summary,
        "by_category": by_category,
        "cases": results,
    }
    OUTPUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    run_evaluation()
