import os

import pytest

from shared.llm import generate_response


@pytest.mark.skipif(
    os.getenv("RUN_GROQ_INTEGRATION") != "1",
    reason="Set RUN_GROQ_INTEGRATION=1 to opt into a live Groq API test.",
)
def test_live_groq_api_returns_text(monkeypatch):
    if not os.getenv("GROQ_API_KEY"):
        pytest.skip("GROQ_API_KEY is not configured.")

    monkeypatch.setenv("LLM_PROVIDER", "groq")
    response = generate_response(
        'Return exactly the JSON object {"status":"ok"}.',
        system_prompt="Return valid JSON only.",
    )
    assert '"status"' in response
    assert '"ok"' in response
