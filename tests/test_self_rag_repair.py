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
