import pytest
from app.generator import repair_hallucinated_answer
from app.evaluator import verify_generated_answer


def test_repair_no_op_when_already_verified():
    chunks = [{"citation_id": 1, "parent_text": "Uptime is 99.9%."}]
    initial_eval = {"status": "SYNTHESIZE"}
    answer = "Uptime is 99.9% [1]."
    eval_result = verify_generated_answer(answer, chunks, initial_eval)

    repaired_answer, repaired_eval, was_repaired = repair_hallucinated_answer(
        "What is the uptime?", answer, chunks, eval_result
    )
    assert was_repaired is False
    assert repaired_answer == answer
    assert repaired_eval["citation_verified"] is True
    assert repaired_eval["invalid_citations"] == []


def test_repair_excises_invalid_citation():
    chunks = [{"citation_id": 1, "parent_text": "Uptime is 99.9%."}]
    initial_eval = {"status": "SYNTHESIZE"}
    # Contains a valid claim [1] and a hallucinated citation [9]
    bad_answer = "Uptime is 99.9% [1]. Backup is scheduled hourly [9]."
    eval_result = verify_generated_answer(bad_answer, chunks, initial_eval)
    assert 9 in eval_result["invalid_citations"]

    repaired_answer, repaired_eval, was_repaired = repair_hallucinated_answer(
        "What is the uptime?", bad_answer, chunks, eval_result
    )
    assert was_repaired is True
    assert "99.9%" in repaired_answer
    assert "[1]" in repaired_answer
    assert "[9]" not in repaired_answer
    assert "hourly" not in repaired_answer
    assert repaired_eval["invalid_citations"] == []
    assert repaired_eval["citation_verified"] is True
    assert repaired_eval.get("self_rag_repaired") is True


def test_repair_falls_back_when_all_claims_hallucinated(monkeypatch):
    from app import generator
    monkeypatch.setattr(generator, "has_valid_primary_key", lambda: False)
    monkeypatch.setattr(generator, "has_valid_fallback_key", lambda: False)

    chunks = [{"citation_id": 1, "child_text": "System availability is 99.9% guaranteed.", "parent_text": "System availability is 99.9% guaranteed."}]
    initial_eval = {"status": "SYNTHESIZE"}
    bad_answer = "Everything is completely made up and nothing cites sources."
    eval_result = verify_generated_answer(bad_answer, chunks, initial_eval)

    repaired_answer, repaired_eval, was_repaired = repair_hallucinated_answer(
        "What guarantee applies?", bad_answer, chunks, eval_result
    )
    assert was_repaired is True
    assert "System availability is 99.9% guaranteed" in repaired_answer
    assert "[1]" in repaired_answer
    assert repaired_eval.get("self_rag_repaired") is True


def test_repair_excises_short_uncited_claim_and_supports_bulleted_source():
    chunks = [{"citation_id": 1, "parent_text": "- Uptime is 99.9%."}]
    initial_eval = {"status": "SYNTHESIZE"}
    bad_answer = "Uptime is 99.9%. [1] Everything failed."
    eval_result = verify_generated_answer(bad_answer, chunks, initial_eval)
    assert any(c["status"] == "unsupported" for c in eval_result["claims"])

    repaired_answer, repaired_eval, was_repaired = repair_hallucinated_answer(
        "What is the uptime?", bad_answer, chunks, eval_result
    )
    assert was_repaired is True
    assert "Everything failed" not in repaired_answer
    assert not any(c["status"] == "unsupported" for c in repaired_eval["claims"])
    assert repaired_eval["claims"][0]["status"] == "supported"


def test_markdown_headings_and_colons_not_treated_as_unsupported_claims():
    chunks = [
        {"citation_id": 1, "parent_text": "Copyright lasts for 50 years after death."},
        {"citation_id": 2, "parent_text": "IP protects creations of the mind in tangible form."},
    ]
    initial_eval = {"status": "SYNTHESIZE"}
    answer = (
        "IP protects creations of the mind once put in tangible form [2].\n\n"
        "### Key Purposes\n"
        "IP serves several critical functions:\n"
        "* Encourages innovation by rewarding creators [2].\n"
        "* Copyright lasts for 50 years after death [1]."
    )
    eval_result = verify_generated_answer(answer, chunks, initial_eval)
    assert not any(c["status"] == "unsupported" for c in eval_result["claims"])
    assert eval_result["citation_verified"] is True
    assert eval_result["invalid_citations"] == []

    repaired_answer, repaired_eval, was_repaired = repair_hallucinated_answer(
        "What is IP for?", answer, chunks, eval_result
    )
    assert was_repaired is False
    assert repaired_answer == answer


def test_repair_preserves_headings_and_colons_while_excising_unsupported_claim():
    chunks = [
        {"citation_id": 1, "parent_text": "Copyright lasts for 50 years after death."},
        {"citation_id": 2, "parent_text": "IP protects creations of the mind in tangible form."},
    ]
    initial_eval = {"status": "SYNTHESIZE"}
    bad_answer = (
        "IP protects creations of the mind once put in tangible form [2].\n\n"
        "### Key Purposes\n"
        "IP serves several critical functions:\n"
        "* Copyright lasts for 50 years after death [1].\n"
        "This completely fabricated sentence has no source citation."
    )
    eval_result = verify_generated_answer(bad_answer, chunks, initial_eval)
    assert any(c["status"] == "unsupported" for c in eval_result["claims"])

    repaired_answer, repaired_eval, was_repaired = repair_hallucinated_answer(
        "What is IP for?", bad_answer, chunks, eval_result
    )
    assert was_repaired is True
    assert "### Key Purposes" in repaired_answer
    assert "IP serves several critical functions:" in repaired_answer
    assert "Copyright lasts for 50 years after death [1]" in repaired_answer
    assert "fabricated sentence" not in repaired_answer
    assert not any(c["status"] == "unsupported" for c in repaired_eval["claims"])
    assert repaired_eval["citation_verified"] is True


def test_plain_section_titles_and_unicode_bullets_not_treated_as_unsupported_claims():
    chunks = [
        {"citation_id": 1, "parent_text": "For general authorship, copyright rights last 50 years."},
        {"citation_id": 2, "parent_text": "IP is defined as property rights resulting from original thought."},
        {"citation_id": 3, "parent_text": "IP assets can be bought, sold, or licensed for commercial growth."},
    ]
    initial_eval = {"status": "SYNTHESIZE"}
    answer = (
        "Intellectual Property (IP) serves to protect original works [2] [3].\n\n"
        "Core Functions\n"
        "• Protection of Original Work: IP ensures authors retain control [3].\n"
        "• Economic Value: IP assets can be bought, sold, or licensed [3].\n\n"
        "Legal Basis\n"
        "IP is defined as property rights resulting from original thought [2].\n\n"
        "Duration\n"
        "For general authorship, copyright rights last 50 years [1]."
    )
    eval_result = verify_generated_answer(answer, chunks, initial_eval)
    assert not any(c["status"] == "unsupported" for c in eval_result["claims"])
    assert eval_result["citation_verified"] is True

    repaired_answer, repaired_eval, was_repaired = repair_hallucinated_answer(
        "What is IP for?", answer, chunks, eval_result
    )
    assert was_repaired is False
    assert repaired_answer == answer


