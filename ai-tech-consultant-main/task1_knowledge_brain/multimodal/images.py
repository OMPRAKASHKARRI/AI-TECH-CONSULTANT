"""Optional Claude vision captions for screenshots embedded in help articles."""
from __future__ import annotations
import base64
import os
from urllib.parse import urlparse
import httpx

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

MAX_IMAGE_BYTES = 5 * 1024 * 1024
SUPPORTED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def describe_image_from_url(url: str, *, timeout: float = 15.0) -> str | None:
    """Describe a help-center image with Claude; return None if unavailable.

    Limits downloads and accepted MIME types to reduce SSRF/resource risks.
    The caller should only pass URLs extracted from the configured help center.
    """
    if not os.getenv("ANTHROPIC_API_KEY") or os.getenv("LLM_PROVIDER", "anthropic").lower() != "anthropic":
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or not (parsed.hostname == "brilliantdirectories.com" or parsed.hostname.endswith(".brilliantdirectories.com")):
        return None
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True, headers={"User-Agent": "JD4KnowledgeBrain/1.0"})
        response.raise_for_status()
        final_host = urlparse(str(response.url)).hostname or ""
        if not (final_host == "brilliantdirectories.com" or final_host.endswith(".brilliantdirectories.com")):
            return None
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type not in SUPPORTED_TYPES or len(response.content) > MAX_IMAGE_BYTES:
            return None
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=timeout, max_retries=1)
        result = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
            max_tokens=220,
            system="Describe screenshots for product support retrieval. Report only visible UI labels, steps, warnings, and relevant configuration. If text is unreadable, say so. Do not infer unseen functionality.",
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": content_type, "data": base64.b64encode(response.content).decode("ascii")}},
                {"type": "text", "text": "Summarize the support-relevant details visible in this image in 1-4 sentences."}
            ]}],
        )
        return " ".join(block.text for block in result.content if getattr(block, "type", None) == "text").strip() or None
    except Exception:
        # Ingestion should not fail solely because optional image vision failed.
        return None
