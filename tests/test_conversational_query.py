"""Unit tests for multi-turn conversational query condensation (Harvard HBS pattern)."""
import pytest
from unittest.mock import patch, MagicMock

from app.query_intent import (
    is_context_dependent_query,
    condense_conversational_query,
)


def test_is_context_dependent_query():
    # Standalone queries: should NOT be marked context-dependent
    assert not is_context_dependent_query("What is a cell?")
    assert not is_context_dependent_query("What is the retention period?")
    assert not is_context_dependent_query("Explain Figure 1")
    assert not is_context_dependent_query("What is the minimum service uptime guarantee in Section 2?")

    # Follow-up queries containing anaphoric pronouns or transition phrases: should be marked True
    assert is_context_dependent_query("Does it apply to contractors?")
    assert is_context_dependent_query("What about wire transfers?")
    assert is_context_dependent_query("Who signs off on that?")
    assert is_context_dependent_query("And what is the penalty?")
    assert is_context_dependent_query("Can they be waived?")
    assert is_context_dependent_query("Is there any exception?")


def test_standalone_query_bypasses_condensation():
    query = "What is the minimum service uptime guarantee?"
    history = [
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Welcome to AuditGuard."},
    ]
    # Even with history, a standalone query is returned immediately without LLM overhead
    with patch("app.query_intent._call_fast_llm_for_condensation") as mock_llm:
        condensed = condense_conversational_query(query, history=history)
        mock_llm.assert_not_called()
        assert condensed == query


def test_context_dependent_query_calls_llm_condenser():
    query = "Does it apply to contractors?"
    history = [
        {"role": "user", "content": "What is the 99.9% uptime guarantee?"},
        {"role": "assistant", "content": "The provider guarantees 99.9% availability during business hours [1]."},
    ]
    expected_reformulation = "Does the 99.9% uptime guarantee apply to contractors?"

    with patch("app.query_intent._call_fast_llm_for_condensation", return_value=expected_reformulation) as mock_llm:
        condensed = condense_conversational_query(query, history=history)
        assert condensed == expected_reformulation
        mock_llm.assert_called_once()
        prompt_arg = mock_llm.call_args[0][0]
        assert "99.9% uptime guarantee" in prompt_arg
        assert "Does it apply to contractors?" in prompt_arg


def test_offline_fallback_when_llm_unavailable():
    query = "What about wire transfers?"
    history = [
        {"role": "user", "content": "What are the rules for invoice payments?"},
        {"role": "assistant", "content": "Payments must be made within 30 days."},
    ]
    # When LLM returns empty string (offline or failure)
    with patch("app.query_intent._call_fast_llm_for_condensation", return_value=""):
        condensed = condense_conversational_query(query, history=history)
        assert condensed == "What are the rules for invoice payments?\nWhat about wire transfers?"


def test_backward_compatibility_with_previous_question_string():
    query = "Does that include holidays?"
    # Only previous_question supplied, no history array
    with patch("app.query_intent._call_fast_llm_for_condensation", return_value="") as mock_llm:
        condensed = condense_conversational_query(query, previous_question="What is the response timeline?")
        assert condensed == "What is the response timeline?\nDoes that include holidays?"


def test_chat_endpoint_accepts_history_payload():
    from fastapi.testclient import TestClient
    import app.main as main

    client = TestClient(main.app)
    # Validate Pydantic schema validation for ChatRequest with history
    payload = {
        "doc_id": "nonexistent_doc",
        "query": "Does it apply to contractors?",
        "history": [
            {"role": "user", "content": "What is the SLA?"},
            {"role": "assistant", "content": "99.9% uptime."},
        ],
    }
    res = client.post("/api/chat", json=payload)
    # Status 404 because doc_id doesn't exist, which confirms ChatRequest schema validation succeeded
    assert res.status_code == 404
    assert "Document not loaded" in res.json()["detail"]

