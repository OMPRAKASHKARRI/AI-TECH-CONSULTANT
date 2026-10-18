import os

import pytest

from shared.llm import generate_response


@pytest.mark.skipif(
    os.getenv("RUN_CLAUDE_INTEGRATION") != "1",
    reason="Set RUN_CLAUDE_INTEGRATION=1 to opt into a live Claude API test.",
)
def test_live_claude_api_returns_text():
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY is not configured.")

    response = generate_response(
        'Return exactly the JSON object {"status":"ok"}.',
        system_prompt="Return valid JSON only.",
    )
    assert '"status"' in response
    assert '"ok"' in response
