"""Optional Google model smoke test; ordinary tests require no network access."""
import os
import pytest


@pytest.mark.integration
def test_gemma_endpoint_smoke():
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        pytest.skip("GEMINI_API_KEY is unset")
    from google import genai
    from google.genai import types
    from google.genai.errors import APIError
    import httpx
    from app.core.config import FALLBACK_MODEL
    try:
        with genai.Client(api_key=key, http_options=types.HttpOptions(timeout=10000)) as client:
            response = client.models.generate_content(
                model=os.getenv("GEMINI_INTEGRATION_MODEL", FALLBACK_MODEL),
                contents="Reply with a short greeting.",
            )
    except (httpx.TransportError, TimeoutError, ConnectionError) as exc:
        pytest.skip(f"Endpoint unreachable: {type(exc).__name__}")
    except APIError as exc:
        if int(exc.code or 0) >= 500:
            pytest.skip("Endpoint temporarily unavailable")
        raise
    assert response.text and response.text.strip()
