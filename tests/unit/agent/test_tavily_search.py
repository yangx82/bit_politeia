"""
Unit tests for Bit Politeia Tavily Search API integration:
1. Graceful fallback when TAVILY_API_KEY is not set.
2. Mocking Tavily API JSON response parsing.
3. Resilience against Tavily network errors.
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
from unittest.mock import MagicMock, patch
from app.services.knowledge_base import WebResearcher


class TestTavilySearchIntegration(unittest.TestCase):

    def test_tavily_missing_key_fallback(self):
        """Test _search_tavily returns None when TAVILY_API_KEY is unset."""
        researcher = WebResearcher()
        with patch.dict(os.environ, {}, clear=True):
            res = researcher._search_tavily("latest python features")
            self.assertIsNone(res)

    def test_tavily_api_response_parsing(self):
        """Test _search_tavily parses mock Tavily HTTP response accurately."""
        researcher = WebResearcher()
        mock_payload = {
            "answer": "Python 3.12 introduced improved f-string syntax and per-interpreter GIL.",
            "results": [
                {
                    "title": "Python 3.12 Release Notes",
                    "content": "Full release overview for Python 3.12...",
                    "url": "https://docs.python.org/3/whatsnew/3.12.html",
                    "published_date": "2023-10-02"
                }
            ]
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_payload
        mock_response.raise_for_status.return_value = None

        with patch.dict(os.environ, {"TAVILY_API_KEY": "tvly-test-mock-key"}):
            with patch("app.services.knowledge_base.httpx", MagicMock()) as mock_httpx:
                mock_httpx.post.return_value = mock_response
                results = researcher._search_tavily("python 3.12 features")

                self.assertIsNotNone(results)
                self.assertGreaterEqual(len(results), 2)

                # Check AI Answer summary block
                self.assertEqual(results[0]["title"], "AI Summary Answer (Tavily)")
                self.assertIn("Python 3.12", results[0]["abstract"])

                # Check Web Result entry
                self.assertEqual(results[1]["title"], "Python 3.12 Release Notes")
                self.assertEqual(results[1]["source"], "https://docs.python.org/3/whatsnew/3.12.html")

    def test_tavily_network_error_fallback(self):
        """Test _search_tavily handles HTTP exception gracefully."""
        researcher = WebResearcher()
        with patch.dict(os.environ, {"TAVILY_API_KEY": "tvly-invalid-key"}):
            mock_httpx = MagicMock()
            mock_httpx.post.side_effect = Exception("HTTP 401 Unauthorized")
            with patch("app.services.knowledge_base.httpx", mock_httpx):
                res = researcher._search_tavily("test query")
                self.assertIsNone(res)


if __name__ == "__main__":
    unittest.main()
