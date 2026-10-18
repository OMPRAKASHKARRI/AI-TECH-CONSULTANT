import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import anthropic
import groq
import pytest

from shared import llm
from task3_meeting_scope import agents, approval_store
from task3_meeting_scope.agents import ScopeGenerationError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BOOKSTORE_TRANSCRIPT = (
    PROJECT_ROOT / "task3_meeting_scope" / "transcripts" / "meeting_1_bookstore.txt"
)


def _scope(**overrides):
    result = {
        "project_summary": "Build a responsive online bookstore for browsing and ordering books.",
        "meeting_analysis": {
            "meeting_summary": "The customer described a first-release bookstore website.",
            "requirements": ["Browse books", "Search by title or author", "Customer accounts"],
            "decisions": ["Online payments are out of scope"],
            "constraints": ["The customer will provide website content"],
            "open_questions": ["Which email service will send order updates?"],
            "out_of_scope_candidates": ["Native mobile application"],
        },
        "deliverables": ["Responsive storefront", "Book catalog and search", "Customer login"],
        "tasks": [
            {
                "task": "Implement the book catalog and search",
                "description": "Build browsing, title/author search, and detail views.",
                "estimate_low_hours": 18,
                "estimate_likely_hours": 24,
                "estimate_high_hours": 36,
                "dependencies": ["Customer-provided book catalog"],
                "notes": "Planning range only.",
                "estimate_hours": 24,
                "rationale": "Build browsing, title and author search, and detail pages.",
            }
        ],
        "assumptions": ["The customer supplies the book content."],
        "exclusions": ["Online payments", "Native mobile application"],
        "risks": ["Email delivery depends on a selected email provider."],
        "dependencies": ["Customer-provided book catalog and images"],
        "open_questions": ["Which email service will send order updates?"],
    }
    result.update(overrides)
    return result


def _task1_response(monkeypatch, *, failure=None, captured=None):
    def post(url, *, json, timeout):
        if captured is not None:
            captured.update(url=url, payload=json, timeout=timeout)
        if failure:
            raise failure

        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "answer": "The product supports catalog browsing and customer accounts.",
                "sources": [
                    {
                        "source_id": "catalog-doc",
                        "title": "Catalog setup",
                        "url": "https://support.example.test/catalog",
                        "snippet": "Catalog browsing setup instructions.",
                        "score": 0.91,
                    }
                ],
                "needs_human_help": False,
            },
        )

    monkeypatch.setattr(agents.requests, "post", post)


def test_llm_adapter_uses_installed_anthropic_supported_parameters(monkeypatch):
    received = {}

    class FakeClient:
        def __init__(self, *, api_key, timeout, max_retries):
            received["client"] = {
                "api_key": api_key,
                "timeout": timeout,
                "max_retries": max_retries,
            }
            self.messages = self

        def create(self, **kwargs):
            received["create"] = kwargs
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text='{"ok": true}')]
            )

    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "unit-test-key")
    monkeypatch.setenv("ANTHROPIC_MODEL", "test-model")
    monkeypatch.setenv("LLM_MAX_TOKENS", "123")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")

    result = llm.generate_response("prompt", system_prompt="system")

    supported = inspect.signature(
        anthropic.resources.messages.Messages.create
    ).parameters
    assert set(received["create"]).issubset(supported)
    assert {"model", "max_tokens", "messages", "system"} <= set(received["create"])
    assert "temperature" not in received["create"]
    assert received["create"]["model"] == "test-model"
    assert received["create"]["max_tokens"] == 123
    assert received["client"] == {
        "api_key": "unit-test-key",
        "timeout": 60.0,
        "max_retries": 2,
    }
    assert result == '{"ok": true}'


@pytest.mark.parametrize(
    ("sdk_error", "safe_error"),
    [
        ("AuthenticationError", llm.LLMAuthenticationError),
        ("RateLimitError", llm.LLMRateLimitError),
        ("APIConnectionError", llm.LLMTemporaryError),
    ],
)
def test_llm_adapter_reports_claude_api_failures_safely(
    monkeypatch, sdk_error, safe_error
):
    class FakeClient:
        def __init__(self, **_kwargs):
            self.messages = self

        def create(self, **_kwargs):
            raise getattr(fake_sdk, sdk_error)("test provider failure")

    fake_sdk = SimpleNamespace(
        Anthropic=FakeClient,
        AuthenticationError=type("AuthenticationError", (Exception,), {}),
        RateLimitError=type("RateLimitError", (Exception,), {}),
        APIConnectionError=type("APIConnectionError", (Exception,), {}),
        InternalServerError=type("InternalServerError", (Exception,), {}),
        APIStatusError=type(
            "APIStatusError",
            (Exception,),
            {"status_code": 400},
        ),
    )
    monkeypatch.setitem(__import__("sys").modules, "anthropic", fake_sdk)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "unit-test-key")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")

    with pytest.raises(safe_error):
        llm.generate_response("prompt")


def test_groq_adapter_uses_supported_parameters_and_configured_model(monkeypatch):
    received = {}

    class FakeCompletions:
        def create(self, **kwargs):
            received["request"] = kwargs
            return SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content='{"status":"ok"}')
                )]
            )

    class FakeGroq:
        def __init__(self, *, api_key, timeout, max_retries):
            received["client"] = (api_key, timeout, max_retries)
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(groq, "Groq", FakeGroq)
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "groq-unit-secret")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("LLM_MAX_TOKENS", "777")

    result = llm.generate_response("prompt", system_prompt="system")

    supported = inspect.signature(
        groq.resources.chat.completions.Completions.create
    ).parameters
    assert set(received["request"]).issubset(supported)
    assert received["request"]["model"] == "openai/gpt-oss-120b"
    assert received["request"]["max_tokens"] == 777
    assert "temperature" not in received["request"]
    assert received["client"] == ("groq-unit-secret", 90.0, 2)
    assert "groq-unit-secret" not in repr(received["request"])
    assert result == '{"status":"ok"}'


def test_groq_is_the_default_provider_and_missing_key_is_explicit(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(llm.LLMConfigurationError, match="GROQ_API_KEY is missing"):
        llm.generate_response("prompt")


@pytest.mark.parametrize(
    ("error_type", "status_code", "expected_error", "message"),
    [
        ("AuthenticationError", 401, llm.LLMAuthenticationError, "authentication failed"),
        ("RateLimitError", 429, llm.LLMRateLimitError, "quota"),
        ("APIConnectionError", None, llm.LLMTemporaryError, "network request failed"),
        ("InternalServerError", 503, llm.LLMTemporaryError, "temporarily unavailable"),
        ("APIStatusError", 404, llm.LLMConfigurationError, "model .* unavailable"),
    ],
)
def test_groq_errors_are_sanitized_and_classified(
    monkeypatch, error_type, status_code, expected_error, message
):
    class ProviderFailure(Exception):
        def __init__(self, *_args, **_kwargs):
            super().__init__("provider diagnostic containing groq-unit-secret")
            self.status_code = status_code
            self.body = {"error": {"code": "model_not_found"}}

    class FakeCompletions:
        def create(self, **_kwargs):
            raise getattr(fake_sdk, error_type)()

    class FakeGroq:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    fake_sdk = SimpleNamespace(
        Groq=FakeGroq,
        AuthenticationError=type("AuthenticationError", (ProviderFailure,), {}),
        RateLimitError=type("RateLimitError", (ProviderFailure,), {}),
        APIConnectionError=type("APIConnectionError", (ProviderFailure,), {}),
        InternalServerError=type("InternalServerError", (ProviderFailure,), {}),
        APIStatusError=type("APIStatusError", (ProviderFailure,), {}),
    )
    monkeypatch.setitem(__import__("sys").modules, "groq", fake_sdk)
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "groq-unit-secret")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-120b")

    with pytest.raises(expected_error, match=message) as raised:
        llm.generate_response("prompt")
    assert "groq-unit-secret" not in str(raised.value)
    assert "provider diagnostic" not in str(raised.value)


def test_bookstore_transcript_reaches_generation_and_task1_http_api(monkeypatch):
    transcript = BOOKSTORE_TRANSCRIPT.read_text(encoding="utf-8")
    api_call = {}
    prompts = []
    _task1_response(monkeypatch, captured=api_call)
    monkeypatch.setattr(
        agents,
        "generate_response",
        lambda prompt, **_kwargs: prompts.append(prompt) or json.dumps(_scope()),
    )

    result = agents.generate_project_scope(transcript)

    assert "online bookstore website" in prompts[0].lower()
    assert api_call["url"].endswith("/knowledge/ask")
    assert transcript in api_call["payload"]["question"]
    assert result["deliverables"]
    assert result["tasks"][0]["estimate_likely_hours"] == 24
    assert result["tasks"][0]["estimate_low_hours"] == 18
    assert result["tasks"][0]["estimate_high_hours"] == 36
    assert result["tasks"][0]["description"]
    assert result["tasks"][0]["dependencies"] == [
        "Customer-provided book catalog"
    ]
    assert result["effort_estimates"] == {
        "low_hours": 18,
        "likely_hours": 24,
        "high_hours": 36,
    }
    assert result["review_status"] == "draft"
    assert result["knowledge_sources"] == [
        {
            "source_id": "catalog-doc",
            "title": "Catalog setup",
            "url": "https://support.example.test/catalog",
            "snippet": "Catalog browsing setup instructions.",
            "score": 0.91,
        }
    ]
    assert result["approval_required"] is True


def test_scope_totals_are_derived_from_all_task_ranges(monkeypatch):
    _task1_response(monkeypatch)
    scope = _scope()
    scope["tasks"].append({
        "task": "Implement customer accounts",
        "description": "Implement registration and login.",
        "estimate_low_hours": 10,
        "estimate_likely_hours": 15,
        "estimate_high_hours": 20,
    })
    monkeypatch.setattr(
        agents, "generate_response", lambda *_args, **_kwargs: json.dumps(scope)
    )

    result = agents.generate_project_scope("Bookstore meeting transcript " * 3)

    assert result["effort_estimates"] == {
        "low_hours": 28,
        "likely_hours": 39,
        "high_hours": 56,
    }
    assert result["estimate_hours"] == 39


def test_approved_baseline_is_included_in_scope_generation_prompt(monkeypatch):
    _task1_response(monkeypatch)
    prompts = []
    monkeypatch.setattr(
        agents,
        "generate_response",
        lambda prompt, **_kwargs: prompts.append(prompt) or json.dumps(_scope()),
    )
    approved_baseline = {
        "project_summary": "Approved bookstore baseline",
        "meeting_analysis": {"requirements": ["Book catalog"]},
        "deliverables": ["Catalog"],
        "tasks": [],
    }

    agents.generate_project_scope(
        "Add order tracking to the bookstore.", previous_scope=approved_baseline
    )

    assert "Approved bookstore baseline" in prompts[0]
    assert "Book catalog" in prompts[0]


@pytest.mark.parametrize(
    "invalid_range",
    [
        {"estimate_low_hours": -1, "estimate_likely_hours": 2, "estimate_high_hours": 3},
        {"estimate_low_hours": 3, "estimate_likely_hours": 2, "estimate_high_hours": 4},
        {"estimate_low_hours": 1, "estimate_likely_hours": 3, "estimate_high_hours": float("inf")},
    ],
)
def test_scope_rejects_invalid_task_estimate_ranges(monkeypatch, invalid_range):
    _task1_response(monkeypatch)
    scope = _scope()
    scope["tasks"][0].update(invalid_range)
    monkeypatch.setattr(
        agents, "generate_response", lambda *_args, **_kwargs: json.dumps(scope)
    )

    with pytest.raises(ScopeGenerationError, match="estimate"):
        agents.generate_project_scope("Bookstore meeting transcript " * 3)


def test_product_knowledge_distinguishes_empty_unavailable_and_malformed(monkeypatch):
    no_sources = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "answer": "No matching product information was found.",
            "sources": [],
            "needs_human_help": True,
        },
    )
    monkeypatch.setattr(agents.requests, "post", lambda *_args, **_kwargs: no_sources)
    empty = agents.retrieve_product_knowledge("bookstore")
    assert empty["status"] == "no_evidence"
    assert empty["sources"] == []

    monkeypatch.setattr(
        agents.requests,
        "post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            agents.requests.ConnectionError("private transport diagnostic")
        ),
    )
    unavailable = agents.retrieve_product_knowledge("bookstore")
    assert unavailable["status"] == "unavailable"
    assert "private transport diagnostic" not in unavailable["error"]

    malformed = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"answer": "some answer", "sources": "not a list"},
    )
    monkeypatch.setattr(
        agents.requests, "post", lambda *_args, **_kwargs: malformed
    )
    invalid = agents.retrieve_product_knowledge("bookstore")
    assert invalid["status"] == "malformed_response"
    assert invalid["sources"] == []


@pytest.mark.parametrize(
    "payload",
    [
        ["not", "an object"],
        {"sources": [], "needs_human_help": True},
        {
            "answer": "Found a source.",
            "sources": [{"title": "Missing URL"}],
            "needs_human_help": False,
        },
    ],
)
def test_task1_malformed_api_payloads_are_reported(monkeypatch, payload):
    malformed = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: payload,
    )
    monkeypatch.setattr(
        agents.requests, "post", lambda *_args, **_kwargs: malformed
    )

    result = agents.retrieve_product_knowledge("bookstore")

    assert result["status"] == "malformed_response"
    assert result["needs_human_help"] is True
    assert result["sources"] == []


def test_scope_generation_parses_markdown_json_fence(monkeypatch):
    _task1_response(monkeypatch)
    response = "```json\n" + json.dumps(_scope()) + "\n```"
    monkeypatch.setattr(agents, "generate_response", lambda *_args, **_kwargs: response)

    result = agents.generate_project_scope("Bookstore meeting transcript " * 3)

    assert result["project_summary"].startswith("Build a responsive")


def test_scope_generation_defaults_missing_optional_fields(monkeypatch):
    _task1_response(monkeypatch)
    monkeypatch.setattr(
        agents,
        "generate_response",
        lambda *_args, **_kwargs: json.dumps(
            {
                "project_summary": "A basic bookstore.",
                "deliverables": ["Book catalog"],
                "tasks": [{
                    "task": "Build the catalog",
                    "description": "Implement the book catalog.",
                    "estimate_likely_hours": 8,
                }],
            }
        ),
    )

    result = agents.generate_project_scope("Bookstore meeting transcript " * 3)

    assert result["tasks"][0]["estimate_low_hours"] == 6
    assert result["tasks"][0]["estimate_high_hours"] == 12
    assert result["assumptions"] == []
    assert result["exclusions"] == []
    assert result["risks"] == []
    assert result["dependencies"] == []
    assert result["open_questions"] == []
    assert result["approval_required"] is True


def test_malformed_json_fails_with_debug_context_and_no_scope(monkeypatch):
    _task1_response(monkeypatch)
    responses = iter(["not json / test-secret", "still not json / test-secret"])
    monkeypatch.setattr(
        agents, "generate_response", lambda *_args, **_kwargs: next(responses)
    )

    with pytest.raises(ScopeGenerationError, match="valid scope JSON response") as error:
        agents.generate_project_scope("Bookstore meeting transcript " * 3)

    assert "No valid JSON object" in str(error.value)
    assert "line" in str(error.value)
    assert "test-secret" not in str(error.value)


def test_empty_scope_response_is_not_reported_as_success(monkeypatch):
    _task1_response(monkeypatch)
    empty = json.dumps({"project_summary": "", "deliverables": [], "tasks": []})
    monkeypatch.setattr(
        agents, "generate_response", lambda *_args, **_kwargs: empty
    )

    with pytest.raises(ScopeGenerationError, match="project_summary"):
        agents.generate_project_scope("Bookstore meeting transcript " * 3)


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (llm.LLMAuthenticationError("Claude authentication failed."), "authentication"),
        (llm.LLMRateLimitError("Claude rate limit reached."), "rate limit"),
        (llm.LLMTemporaryError("Claude is temporarily unavailable."), "temporarily"),
    ],
)
def test_provider_errors_are_distinguished_and_not_retried(
    monkeypatch, failure, message
):
    _task1_response(monkeypatch)
    calls = []

    def fail(*_args, **_kwargs):
        calls.append(True)
        raise failure

    monkeypatch.setattr(agents, "generate_response", fail)

    with pytest.raises(type(failure), match=message):
        agents.generate_project_scope("Bookstore meeting transcript " * 3)
    assert len(calls) == 1


def test_task1_unavailable_keeps_scope_marked_for_product_review(monkeypatch):
    _task1_response(monkeypatch, failure=agents.requests.ConnectionError("offline"))
    monkeypatch.setattr(
        agents, "generate_response", lambda *_args, **_kwargs: json.dumps(_scope())
    )

    result = agents.generate_project_scope("Bookstore meeting transcript " * 3)

    assert result["knowledge_sources"] == []
    assert result["knowledge_status"] == "unavailable"
    assert result["knowledge_review_required"] is True
    assert result["approval_required"] is True


def test_streamlit_shows_scope_and_requires_explicit_approval(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(approval_store, "DB_PATH", str(tmp_path / "scope.sqlite3"))
    monkeypatch.setattr(
        agents,
        "generate_project_scope",
        lambda _transcript, previous_scope=None: _scope(
            knowledge_sources=[
                {
                    "title": "Catalog setup",
                    "url": "https://support.example.test/catalog",
                }
            ],
            knowledge_review_required=False,
            approval_required=True,
        ),
    )

    app = AppTest.from_file(
        str(PROJECT_ROOT / "task3_meeting_scope" / "main.py"),
        default_timeout=20,
    ).run()
    app.text_area(key="meeting_transcript").set_value(
        "Customer: We need an online bookstore and a searchable catalog."
    )
    app.button[0].click().run()

    assert not app.exception
    assert app.session_state["current_scope"]["approval_required"] is True
    assert any(
        "Build a responsive online bookstore" in item.value
        for item in app.markdown
    )
    assert any("Responsive storefront" in item.value for item in app.markdown)
    assert any("Catalog setup" in item.value for item in app.markdown)
    assert "Implement the book catalog and search" in app.dataframe[0].value.to_string()
    assert approval_store.list_scope_decisions() == []

    app.text_input[0].set_value("reviewer-test")
    app.selectbox[0].select("approved")
    app.button[1].click().run()

    assert not app.exception
    assert approval_store.list_scope_decisions()[0]["decision"] == "approved"
    assert app.session_state["current_scope"]["review_status"] == "approved"
    assert app.session_state["current_scope"]["approval_required"] is False


def test_streamlit_shows_generation_error_without_a_draft(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(approval_store, "DB_PATH", str(tmp_path / "scope.sqlite3"))

    def fail(_transcript, previous_scope=None):
        raise llm.LLMAuthenticationError(
            "Groq authentication failed. Verify GROQ_API_KEY."
        )

    monkeypatch.setattr(agents, "generate_project_scope", fail)
    app = AppTest.from_file(
        str(PROJECT_ROOT / "task3_meeting_scope" / "main.py"),
        default_timeout=20,
    ).run()
    app.text_area(key="meeting_transcript").set_value(
        "Customer: We need an online bookstore and a searchable catalog."
    )
    app.button[0].click().run()

    assert not app.exception
    assert app.session_state["current_scope"] is None
    assert any("authentication failed" in item.value.lower() for item in app.error)
    assert approval_store.list_scope_decisions() == []
