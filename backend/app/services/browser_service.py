"""
Playwright Headless Browser Service for Bit Politeia.
Provides real DOM rendering for SPA web pages with automatic fallback to httpx.
"""

import sys
import site
import os

user_site = site.getusersitepackages()
if user_site and user_site not in sys.path:
    sys.path.insert(0, user_site)

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Dynamic import check for Playwright
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.info("Playwright not installed. BrowserService will fallback to static HTTP fetch mode.")


class BrowserService:
    """
    Asynchronous Headless Browser Service using Playwright.
    Manages Playwright lifecycle, pages, and DOM extraction.
    """

    def __init__(self):
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._lock = asyncio.Lock()

    async def _ensure_browser(self):
        """Lazy initialize Playwright Chromium browser."""
        if not PLAYWRIGHT_AVAILABLE:
            return None

        async with self._lock:
            if self._browser and self._browser.is_connected():
                return self._browser

            try:
                logger.info("Initializing Playwright Chromium Headless Driver...")
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
                logger.info("Playwright Headless Chromium successfully started.")
                return self._browser
            except Exception as e:
                logger.warning(f"Failed to launch Playwright browser ({e}). BrowserService will fallback.")
                return None

    async def fetch_page_dom(
        self,
        url: str,
        timeout_ms: int = 15000,
        wait_selector: str | None = None,
        wait_until: str = "domcontentloaded"
    ) -> dict[str, Any]:
        """
        Render a web page using Headless Chromium and extract title & HTML.
        Returns dict: {"success": bool, "title": str, "html": str, "mode": str, "error": str}
        """
        browser = await self._ensure_browser()

        # Graceful Fallback if Playwright is unavailable
        if not browser:
            return {
                "success": False,
                "title": "",
                "html": "",
                "mode": "fallback",
                "error": "Playwright headless driver unavailable"
            }

        context = None
        page = None
        try:
            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 800}
            )
            page = await context.new_page()

            logger.info(f"Playwright rendering: {url} (until={wait_until}, timeout={timeout_ms}ms)...")
            await page.goto(url, wait_until=wait_until, timeout=timeout_ms)

            if wait_selector:
                logger.info(f"Playwright waiting for selector: {wait_selector}...")
                await page.wait_for_selector(wait_selector, timeout=timeout_ms)

            title = await page.title()
            html_content = await page.content()

            return {
                "success": True,
                "title": title,
                "html": html_content,
                "mode": "playwright",
                "error": None
            }

        except Exception as e:
            logger.error(f"Playwright rendering error for {url}: {e}")
            return {
                "success": False,
                "title": "",
                "html": "",
                "mode": "playwright_error",
                "error": str(e)
            }
        finally:
            if page:
                try: await page.close()
                except Exception: pass
            if context:
                try: await context.close()
                except Exception: pass

    async def close(self):
        """Close browser resources."""
        async with self._lock:
            if self._browser:
                try: await self._browser.close()
                except Exception: pass
                self._browser = None
            if self._playwright:
                try: await self._playwright.stop()
                except Exception: pass
                self._playwright = None


# Global Singleton Instance
browser_service = BrowserService()
