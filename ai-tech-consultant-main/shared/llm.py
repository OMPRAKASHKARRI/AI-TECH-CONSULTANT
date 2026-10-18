
"""LLM adapter supporting Groq, Anthropic, Ollama, and offline mode.

Environment variables:
    LLM_PROVIDER=groq | anthropic | ollama | offline
    GROQ_API_KEY=your Groq API key
    GROQ_MODEL=openai/gpt-oss-120b
    ANTHROPIC_API_KEY=your Anthropic API key
    ANTHROPIC_MODEL=claude-sonnet-5-5
    OLLAMA_MODEL=llama3.2
    LLM_MAX_TOKENS=4096
"""

from __future__ import annotations

import json
import os
import re

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class LLMError(RuntimeError):
    """Base class for provider failures."""


class LLMConfigurationError(LLMError):
    """The selected provider is not configured."""


class LLMAuthenticationError(LLMError):
    """The provider rejected its credentials."""


class LLMRateLimitError(LLMError):
    """The provider rate-limited the request."""


class LLMTemporaryError(LLMError):
    """The provider is temporarily unavailable."""


class LLMServiceError(LLMError):
    """The provider rejected a request."""


def _offline_response(prompt: str, system_prompt: str) -> str:
    """Return conservative responses for offline tests."""
    text = f"{system_prompt}\n{prompt}".lower()

    if (
        "category:" in text
        and "urgency:" in text
        and "summary:" in text
    ):
        subject = re.search(r"subject:\s*(.+)", prompt, re.I)
        body = re.search(r"email body:\s*(.+)", prompt, re.I | re.S)

        content = (
            (subject.group(1) if subject else "")
            + " "
            + (body.group(1) if body else "")
        ).lower()

        if any(w in content for w in ("bill", "charged", "payment", "refund")):
            category = "Billing"
        elif any(w in content for w in ("error", "bug", "broken", "crash")):
            category = "Bug Report"
        elif any(
            w in content
            for w in ("login", "password", "cannot", "can't", "issue", "help")
        ):
            category = "Technical Support"
        else:
            category = "Other"

        urgency = (
            "High"
            if any(
                w in content
                for w in ("urgent", "down", "lost access", "charged twice")
            )
            else "Medium"
        )

        return json.dumps({
            "category": category,
            "urgency": urgency,
            "summary": "Offline-mode classification; verify before use.",
        })

    if "project_summary" in prompt and '"tasks"' in prompt:
        raise LLMConfigurationError(
            "Scope generation requires a configured model provider; "
            "offline mode cannot produce a project scope."
        )

    if "return only a valid json object" in text:
        return json.dumps({
            "category": "Other",
            "urgency": "Medium",
            "summary": "Offline mode; human review required.",
        })

    return (
        "Thank you for contacting our support team. We need to verify "
        "the details against our product documentation before providing "
        "specific instructions. A team member will review your request "
        "and follow up.\n\nBest regards,\nSupport Team"
    )


def _max_tokens() -> int:
    try:
        value = int(os.getenv("LLM_MAX_TOKENS", "4096"))
    except ValueError as exc:
        raise LLMConfigurationError(
            "LLM_MAX_TOKENS must be a positive integer."
        ) from exc

    if value <= 0:
        raise LLMConfigurationError(
            "LLM_MAX_TOKENS must be a positive integer."
        )
    return value


def _provider_error_code(exc: Exception) -> str:
    body = getattr(exc, "body", None)
    if not isinstance(body, dict):
        return ""
    error = body.get("error", body)
    if not isinstance(error, dict):
        return ""
    code = error.get("code")
    if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", code):
        return code.lower()
    return ""


def _generate_groq_response(prompt: str, system_prompt: str) -> str:
    """Generate a response using Groq chat completions."""
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise LLMConfigurationError(
            "GROQ_API_KEY is missing. Add it to your .env file."
        )

    try:
        from groq import Groq
    except ImportError as exc:
        raise LLMConfigurationError(
            "Install the Groq SDK using `pip install groq`."
        ) from exc

    model = os.getenv(
        "GROQ_MODEL", "openai/gpt-oss-120b"
    ).strip()
    if not model:
        raise LLMConfigurationError(
            "GROQ_MODEL cannot be empty. Set it to a supported Groq model ID."
        )

    try:
        client = Groq(api_key=api_key, timeout=90.0, max_retries=2)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=_max_tokens(),
        )
    except Exception as exc:
        try:
            from groq import (
                AuthenticationError,
                RateLimitError,
                APIConnectionError,
                InternalServerError,
                APIStatusError,
            )
        except ImportError:
            raise LLMServiceError(
                "Groq request failed. Verify the SDK installation and retry."
            ) from exc

        if isinstance(exc, AuthenticationError):
            raise LLMAuthenticationError(
                "Groq authentication failed. Verify GROQ_API_KEY."
            ) from exc

        if isinstance(exc, RateLimitError):
            raise LLMRateLimitError(
                "Groq rate limit or quota reached. Check the Groq account "
                "limits and retry later."
            ) from exc

        if isinstance(exc, (APIConnectionError, InternalServerError)):
            raise LLMTemporaryError(
                "Groq is temporarily unavailable or the network request "
                "failed. Check connectivity and retry."
            ) from exc

        if isinstance(exc, APIStatusError):
            status_code = getattr(exc, "status_code", 0)
            error_code = _provider_error_code(exc)
            if status_code == 404 or error_code in {
                "model_decommissioned",
                "model_not_found",
                "invalid_model",
            }:
                raise LLMConfigurationError(
                    f"Groq model '{model}' is unavailable. Choose a currently "
                    "supported ID from GROQ_MODEL."
                ) from exc
            if status_code == 400:
                raise LLMServiceError(
                    "Groq rejected the request (HTTP 400). Verify GROQ_MODEL "
                    "and the request configuration."
                ) from exc
            if status_code >= 500:
                raise LLMTemporaryError(
                    f"Groq is temporarily unavailable (HTTP {status_code}). "
                    "Retry the request."
                ) from exc
            raise LLMServiceError(
                f"Groq rejected the request (HTTP {status_code}). "
                "Verify the provider configuration."
            ) from exc

        raise LLMServiceError(
            f"Groq request failed for model '{model}'. "
            "Verify provider configuration and retry."
        ) from exc

    choices = getattr(response, "choices", None)
    if not choices:
        raise LLMServiceError(
            f"Groq returned no completion choices for model '{model}'."
        )
    result = getattr(choices[0].message, "content", None)
    if not isinstance(result, str) or not result.strip():
        raise LLMServiceError(
            f"Groq returned empty text for model '{model}'."
        )

    return result.strip()


def _generate_anthropic_response(
    prompt: str, system_prompt: str
) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise LLMConfigurationError(
            "ANTHROPIC_API_KEY is missing."
        )

    try:
        import anthropic
    except ImportError as exc:
        raise LLMConfigurationError(
            "Install the Anthropic SDK using `pip install anthropic`."
        ) from exc

    model = os.getenv(
        "ANTHROPIC_MODEL", "claude-sonnet-5-5"
    ).strip()

    try:
        client = anthropic.Anthropic(
            api_key=api_key, timeout=60.0, max_retries=2
        )
        response = client.messages.create(
            model=model,
            max_tokens=_max_tokens(),
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError as exc:
        raise LLMAuthenticationError(
            "Claude authentication failed. Verify ANTHROPIC_API_KEY."
        ) from exc
    except anthropic.RateLimitError as exc:
        raise LLMRateLimitError(
            "Claude rate limit or quota reached. Check the Anthropic account "
            "limits and retry later."
        ) from exc
    except (
        anthropic.APIConnectionError,
        anthropic.InternalServerError,
    ) as exc:
        raise LLMTemporaryError(
            "Claude is temporarily unavailable or the network request failed. "
            "Check connectivity and retry."
        ) from exc
    except anthropic.APIStatusError as exc:
        status_code = getattr(exc, "status_code", 0)
        if status_code == 404:
            raise LLMConfigurationError(
                f"Claude model '{model}' is unavailable. Verify ANTHROPIC_MODEL."
            ) from exc
        if status_code == 400:
            raise LLMServiceError(
                "Claude rejected the request (HTTP 400). Verify "
                "ANTHROPIC_MODEL and the request configuration."
            ) from exc
        if status_code >= 500:
            raise LLMTemporaryError(
                f"Claude is temporarily unavailable (HTTP {status_code}). "
                "Retry the request."
            ) from exc
        raise LLMServiceError(
            f"Claude API rejected the request (HTTP {status_code}). "
            "Verify provider configuration."
        ) from exc

    result = "\n".join(
        block.text
        for block in response.content
        if getattr(block, "type", None) == "text"
    ).strip()

    if not result:
        raise LLMServiceError("Claude returned no text content.")

    return result


def _generate_ollama_response(
    prompt: str, system_prompt: str
) -> str:
    try:
        import ollama
    except ImportError as exc:
        raise LLMConfigurationError(
            "Install Ollama's Python SDK using `pip install ollama`."
        ) from exc

    model = os.getenv("OLLAMA_MODEL", "llama3.2").strip()

    try:
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            options={"temperature": 0},
        )
    except Exception as exc:
        raise LLMServiceError(
            f"Ollama request failed for model '{model}'. "
            "Verify the local service and model configuration."
        ) from exc

    return response["message"]["content"]


def generate_response(
    prompt: str,
    system_prompt: str = "You are a helpful AI assistant.",
) -> str:
    """Generate text with the provider selected in the environment."""
    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()

    if provider == "groq":
        return _generate_groq_response(prompt, system_prompt)

    if provider == "anthropic":
        return _generate_anthropic_response(prompt, system_prompt)

    if provider == "ollama":
        return _generate_ollama_response(prompt, system_prompt)

    if provider == "offline":
        if "project_summary" in prompt and '"tasks"' in prompt:
            raise LLMConfigurationError(
                "Scope generation requires a configured model provider; "
                "offline mode cannot produce a project scope."
            )
        return _offline_response(prompt, system_prompt)

    raise LLMConfigurationError(
        "LLM_PROVIDER must be groq, anthropic, ollama, or offline."
    )
