
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from task1_knowledge_brain.database import save_article, start_ingestion_run, update_ingestion_run, get_latest_ingestion_run

SITEMAP_URL = (
    "https://support.brilliantdirectories.com/support/sitemap.xml"
)


def get_sitemap_urls(max_pages: int | None = 20) -> list[str]:
    """Read article URLs from the help-center sitemap."""
    response = httpx.get(
        SITEMAP_URL,
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": "JD4KnowledgeBrain/1.0"},
    )
    response.raise_for_status()

    root = ET.fromstring(response.content)
    urls = [
        node.text.strip()
        for node in root.iter()
        if node.tag.endswith("loc") and node.text
    ]

    # Support both a sitemap index and a normal URL sitemap.
    if urls and all(urlparse(url).path.endswith(".xml") for url in urls):
        expanded = []
        for sitemap_url in urls:
            sitemap_response = httpx.get(
                sitemap_url,
                timeout=30,
                follow_redirects=True,
                headers={"User-Agent": "JD4KnowledgeBrain/1.0"},
            )
            sitemap_response.raise_for_status()
            sitemap_root = ET.fromstring(sitemap_response.content)
            expanded.extend(
                node.text.strip()
                for node in sitemap_root.iter()
                if node.tag.endswith("loc") and node.text
            )
        urls = expanded

    # Do not crawl arbitrary hosts from a sitemap response.
    urls = [candidate for candidate in urls
            if urlparse(candidate).scheme == "https"
            and urlparse(candidate).hostname == "support.brilliantdirectories.com"]
    if max_pages is not None:
        urls = urls[:max_pages]

    return urls


def crawl_article(url: str) -> dict | None:
    """Extract readable text from one help-center article."""
    try:
        response = httpx.get(
            url,
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "JD4KnowledgeBrain/1.0"},
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        for element in soup.select(
            "script, style, nav, footer, header, noscript"
        ):
            element.decompose()

        main = soup.find("main") or soup.find("article") or soup.body
        if main is None:
            return None

        title_tag = soup.find("h1") or soup.find("title")
        title = (
            title_tag.get_text(" ", strip=True)
            if title_tag
            else url
        )
        content = main.get_text(" ", strip=True)
        # Preserve information carried by screenshots and diagrams even when
        # vision credentials are not configured. Vision descriptions are added
        # when Claude is available; alt text remains the safe fallback.
        image_notes = []
        from task1_knowledge_brain.multimodal.images import describe_image_from_url
        for image_index, image in enumerate(main.select("img")[:12]):
            src = image.get("src") or image.get("data-src") or ""
            if src and not src.startswith(("data:", "javascript:")):
                from urllib.parse import urljoin
                image_url = urljoin(url, src)
                alt = image.get("alt", "").strip()
                caption = image.find_parent("figure")
                caption_text = caption.get_text(" ", strip=True) if caption else ""
                note = f"Image: {alt or 'Screenshot without alt text'}. URL: {image_url}"
                if caption_text and caption_text != alt:
                    note += f". Caption: {caption_text}"
                # Limit paid vision calls to the first two images per article.
                if image_index < 2:
                    vision_summary = describe_image_from_url(image_url)
                    if vision_summary:
                        note += f". Claude visual description: {vision_summary}"
                image_notes.append(note)
        if image_notes:
            content += "\n\nSCREENSHOTS AND DIAGRAMS:\n" + "\n".join(image_notes)

        if len(content) < 80:
            return None

        return {
            "url": url,
            "title": title,
            "content": content,
        }

    except (httpx.HTTPError, ET.ParseError) as exc:
        print(f"Could not crawl {url}: {exc}")
        return None


def sync_articles(
    max_pages: int | None = 20,
    delay_seconds: float = 1.0,
) -> dict:
    """Fetch sitemap articles and save successfully extracted content."""
    urls = get_sitemap_urls(max_pages=max_pages)
    saved = 0
    failed = 0
    processed = 0
    previous_run = get_latest_ingestion_run()
    resume_at = 0
    if previous_run and previous_run.get("status") == "running":
        run_id = int(previous_run["id"])
        saved = int(previous_run.get("saved", 0))
        failed = int(previous_run.get("failed", 0))
        processed = int(previous_run.get("processed", 0))
        current_url = previous_run.get("current_url")
        if current_url in urls:
            resume_at = urls.index(current_url) + 1
        else:
            # Sitemap changed while a run was interrupted; restart safely from
            # the beginning rather than skipping URLs using stale offsets.
            saved = failed = processed = 0
            current_url = None
            resume_at = 0
        update_ingestion_run(run_id, processed=processed, saved=saved, failed=failed, current_url=current_url, status="running")
    else:
        run_id = start_ingestion_run(len(urls))

    # Each successfully processed URL is checkpointed after its article has
    # been persisted. A restarted process resumes after the last checkpoint.
    for index, url in enumerate(urls[resume_at:], start=resume_at + 1):
        article = crawl_article(url)

        if article:
            save_article(
                article["url"],
                article["title"],
                article["content"],
            )
            saved += 1
            print(f"[{index}/{len(urls)}] Saved: {article['title']}")
        else:
            failed += 1
            print(f"[{index}/{len(urls)}] Skipped: {url}")

        processed = index
        update_ingestion_run(run_id, processed=processed, saved=saved, failed=failed, current_url=url)
        if index < len(urls):
            time.sleep(delay_seconds)

    update_ingestion_run(run_id, processed=processed, saved=saved, failed=failed, status="completed")
    return {
        "run_id": run_id,
        "status": "completed",
        "discovered": len(urls),
        "processed": processed,
        "saved": saved,
        "failed": failed,
    }
