"""Answer presentation must retain source conditions and work without an LLM."""
import app.generator as generator


def test_offline_answer_leads_with_matched_passage_and_keeps_complete_evidence(monkeypatch):
    monkeypatch.setattr(generator, "has_valid_primary_key", lambda: False)
    monkeypatch.setattr(generator, "has_valid_fallback_key", lambda: False)
    clause = "A 15% credit applies below 99.5% availability."
    context = clause + " Claims must be filed within 30 days. Planned maintenance is excluded."
    chunks = [{"citation_id": 3, "child_text": clause, "parent_text": context}]
    answer, telemetry = generator.generate_grounded_answer_with_telemetry("What credit applies?", chunks)
    lead, evidence = answer.split("### Source excerpts")
    assert clause + " [3]" in lead
    assert context in evidence
    assert "### Source [3]" in evidence
    assert telemetry["generation_mode"] == "extractive_fallback"
    assert "".join(generator.stream_grounded_answer("What credit applies?", chunks)) == answer


def test_conflict_remains_above_collapsed_evidence(monkeypatch):
    monkeypatch.setattr(generator, "detect_heuristic_discrepancy", lambda *a: {
        "status": "CONTRADICTION", "discrepancy_delta": "The reported values differ."
    })
    answer = generator._build_extractive_fallback("Compare uptime", [
        {"citation_id": 1, "parent_text": "Target is 99.9%."},
        {"citation_id": 2, "parent_text": "Actual is 98.2%.", "dense_score": .8},
    ])
    assert "### Conflicting evidence" in answer.split("### Source excerpts")[0]
    assert "[1][2]" in answer
    assert "Actual is 98.2%." in answer


def test_empty_sources_still_refuse():
    assert generator._build_extractive_fallback("Anything?", []) == (
        "I cannot verify this information in the provided document excerpts."
    )
