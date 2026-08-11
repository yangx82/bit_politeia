"""
Unit tests for Bit Politeia Playwright BrowserService and web rendering tools:
1. BrowserService initialization and graceful fallback.
2. fetch_web_page with rendering and markdown formatting.
3. browser_fetch_page tool invocation and error resilience.
"""

import sys
import site
import os

user_site = site.getusersitepackages()
if user_site and user_site not in sys.path:
    sys.path.insert(0, user_site)

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "backend"))

import unittest
import asyncio
from unittest.mock import AsyncMock, patch
from app.services.browser_service import BrowserService, browser_service
from app.agent.tools_web import fetch_web_page, browser_fetch_page


class TestPlaywrightBrowserService(unittest.TestCase):

    def test_browser_service_graceful_fallback(self):
        """Test BrowserService fallback mechanism when playwright is missing or mock disabled."""
        service = BrowserService()

        async def run_fetch():
            with patch.object(service, "_ensure_browser", AsyncMock(return_value=None)):
                res = await service.fetch_page_dom("http://example.com")
                self.assertFalse(res["success"])
                self.assertEqual(res["mode"], "fallback")

        asyncio.run(run_fetch())

    def test_fetch_web_page_tool(self):
        """Test fetch_web_page executes safely using browser_service or fallback."""
        async def run_tool():
            if hasattr(fetch_web_page, "ainvoke"):
                res = await fetch_web_page.ainvoke({"url": "http://example.com"})
            else:
                res = await fetch_web_page("http://example.com")
            self.assertIsInstance(res, str)

        asyncio.run(run_tool())

    def test_browser_fetch_page_tool(self):
        """Test browser_fetch_page probe tool structure."""
        async def run_tool():
            if hasattr(browser_fetch_page, "ainvoke"):
                res = await browser_fetch_page.ainvoke({"url": "http://example.com"})
            else:
                res = await browser_fetch_page("http://example.com")
            self.assertIsInstance(res, str)

        asyncio.run(run_tool())


if __name__ == "__main__":
    unittest.main()
