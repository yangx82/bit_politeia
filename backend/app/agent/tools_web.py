
"""
Web tools for Agent.
Ported/Adapted from Nanobot's agent/tools/web.py
"""

import html
import json
import logging
import re
from typing import Optional
from langchain_core.tools import tool
import httpx

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
    text = re.sub(r'<script[\s\S]*?</script>', '', text, flags=re.I)
    text = re.sub(r'<style[\s\S]*?</style>', '', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    return html.unescape(text).strip()

def _normalize_text(text: str) -> str:
    """Normalize whitespace."""
    text = re.sub(r'[ \t]+', ' ', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()

def _to_markdown(html_content: str) -> str:
    """Convert HTML to simple markdown."""
    text = html_content
    # Links
    text = re.sub(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
                  lambda m: f'[{_strip_tags(m[2])}]({m[1]})', text, flags=re.I)
    # Headings
    text = re.sub(r'<h([1-6])[^>]*>([\s\S]*?)</h\1>',
                  lambda m: f'\n{"#" * int(m[1])} {_strip_tags(m[2])}\n', text, flags=re.I)
    # Lists
    text = re.sub(r'<li[^>]*>([\s\S]*?)</li>', lambda m: f'\n- {_strip_tags(m[1])}', text, flags=re.I)
    # Blocks
    text = re.sub(r'</(p|div|section|article)>', '\n\n', text, flags=re.I)
    text = re.sub(r'<(br|hr)\s*/?>', '\n', text, flags=re.I)
    
    return _normalize_text(_strip_tags(text))

@tool
async def fetch_web_page(url: str, extract_mode: str = "markdown") -> str:
    """
    Fetch a URL and extract its content. 
    Use this to read documentation, articles, or other web pages found via search.
    
    Args:
        url: The URL to fetch.
        extract_mode: "markdown" (default) or "text" (plain text).
    """
    try:
        if not HAS_READABILITY:
            return "Error: readability-lxml library not installed. Please install it to use this tool."

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": USER_AGENT}
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            
        content_type = response.headers.get("content-type", "").lower()
        
        # 1. JSON
        if "application/json" in content_type:
            return json.dumps(response.json(), indent=2)
            
        # 2. HTML
        if "text/html" in content_type:
            doc = Document(response.text)
            title = doc.title()
            summary_html = doc.summary() # Readability's main content extraction
            
            if extract_mode == "markdown":
                content = _to_markdown(summary_html)
                return f"# {title}\n\n{content}\n\nSource: {url}"
            else:
                content = _strip_tags(summary_html)
                return f"Title: {title}\n\n{content}\n\nSource: {url}"
                
        # 3. Plain Text / Other
        return response.text[:50000] # Cap at 50k chars
        
    except Exception as e:
        return f"Error fetching URL {url}: {str(e)}"
