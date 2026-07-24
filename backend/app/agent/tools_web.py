"""
Web tools for Agent.
Ported/Adapted from Nanobot's agent/tools/web.py
"""

import html
import json
import logging
import re

try:
    import httpx
except ImportError:
    httpx = None

try:
    from langchain_core.tools import tool
except ImportError:
    def tool(func):
        return func

# Optional: Readability
try:
    from readability import Document

    HAS_READABILITY = True
except ImportError:
    HAS_READABILITY = False

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _strip_tags(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _normalize_text(text: str) -> str:
    """Normalize whitespace."""
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _to_markdown(html_content: str) -> str:
    """Convert HTML to simple markdown."""
    text = html_content
    # Links
    text = re.sub(
        r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
        lambda m: f"[{_strip_tags(m[2])}]({m[1]})",
        text,
        flags=re.I,
    )
    # Headings
    text = re.sub(
        r"<h([1-6])[^>]*>([\s\S]*?)</h\1>",
        lambda m: f"\n{'#' * int(m[1])} {_strip_tags(m[2])}\n",
        text,
        flags=re.I,
    )
    # Lists
    text = re.sub(
        r"<li[^>]*>([\s\S]*?)</li>", lambda m: f"\n- {_strip_tags(m[1])}", text, flags=re.I
    )
    # Blocks
    text = re.sub(r"</(p|div|section|article)>", "\n\n", text, flags=re.I)
    text = re.sub(r"<(br|hr)\s*/?>", "\n", text, flags=re.I)

    return _normalize_text(_strip_tags(text))


@tool
async def fetch_web_page(url: str, extract_mode: str = "markdown") -> str:
    """
    Fetch a URL and extract its content with Playwright Headless rendering & HTTP fallback.
    Use this to read documentation, articles, or other web pages found via search.

    Args:
        url: The URL to fetch.
        extract_mode: "markdown" (default) or "text" (plain text).
    """
    try:
        from ..services.browser_service import browser_service

        # 1. Try Playwright Headless Chromium Rendering
        render_res = await browser_service.fetch_page_dom(url)
        if render_res.get("success") and render_res.get("html"):
            html_text = render_res["html"]
            title = render_res.get("title", "Rendered Page")

            if HAS_READABILITY:
                try:
                    doc = Document(html_text)
                    title = doc.title() or title
                    html_text = doc.summary()
                except Exception:
                    pass

            if extract_mode == "markdown":
                content = _to_markdown(html_text)
                return f"# {title}\n\n{content}\n\nSource: {url} (Rendered via Playwright Chromium)"
            else:
                content = _strip_tags(html_text)
                return f"Title: {title}\n\n{content}\n\nSource: {url} (Rendered via Playwright Chromium)"

        # 2. Fallback to HTTP Client
        logger.info(f"Using HTTP fallback fetch for {url} (Reason: {render_res.get('error') or 'Fallback mode'})")
        if not HAS_READABILITY:
            return (
                "Error: readability-lxml library not installed. Please install it to use this tool."
            )

        async with httpx.AsyncClient(
            follow_redirects=True, timeout=30.0, headers={"User-Agent": USER_AGENT}
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        content_type = response.headers.get("content-type", "").lower()

        # JSON
        if "application/json" in content_type:
            return json.dumps(response.json(), indent=2)

        # HTML
        if "text/html" in content_type:
            doc = Document(response.text)
            title = doc.title()
            summary_html = doc.summary()

            if extract_mode == "markdown":
                content = _to_markdown(summary_html)
                return f"# {title}\n\n{content}\n\nSource: {url}"
            else:
                content = _strip_tags(summary_html)
                return f"Title: {title}\n\n{content}\n\nSource: {url}"

        return response.text[:50000]

    except Exception as e:
        return f"Error fetching URL {url}: {e!s}"


@tool
async def browser_fetch_page(url: str, wait_selector: str = None, extract_mode: str = "markdown") -> str:
    """
    Render a web page using Playwright Headless Chromium browser.
    Use this for dynamic SPA pages (React/Vue/Angular), pages requiring JavaScript execution, or deep web rendering.

    Args:
        url: The web page URL to render.
        wait_selector: Optional CSS selector to wait for before extracting DOM (e.g. 'article', '.content').
        extract_mode: "markdown" (default) or "text".
    """
    try:
        from ..services.browser_service import browser_service

        res = await browser_service.fetch_page_dom(url, wait_selector=wait_selector)
        if not res.get("success"):
            return f"Browser Fetch Failed ({res.get('mode')}): {res.get('error')}. Falling back to standard fetch...\n\n" + await fetch_web_page(url, extract_mode=extract_mode)

        html_text = res["html"]
        title = res.get("title", "Rendered Page")

        if HAS_READABILITY:
            try:
                doc = Document(html_text)
                title = doc.title() or title
                html_text = doc.summary()
            except Exception:
                pass

        if extract_mode == "markdown":
            content = _to_markdown(html_text)
            return f"# {title}\n\n{content}\n\nSource: {url} [Playwright Headless]"
        else:
            content = _strip_tags(html_text)
            return f"Title: {title}\n\n{content}\n\nSource: {url} [Playwright Headless]"

    except Exception as e:
        return f"Error rendering browser page {url}: {e!s}"


@tool
async def academic_research(topic: str) -> str:
    """
    Conducts deep research on scientific or technical topics using ArXiv and BioRxiv.
    Use this ONLY when the user's request specifically requires external scientific validation,
    latest research context, or technical evidence.
    DO NOT use for simple P2P greetings, status checks, or routine community tasks.

    Args:
        topic: The scientific or technical topic to research.
    """
    from ..services.knowledge_base import knowledge_base

    logger.info(f"Explicit academic research triggered for topic: {topic}")
    return knowledge_base.search_web_and_context(topic)
