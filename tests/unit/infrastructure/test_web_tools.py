"""Tests for web_search and web_fetch tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from infrastructure.local_execution.tools.web_tools import (
    _html_to_text,
    _parse_ddg_results,
    _strip_html,
    web_fetch,
    web_search,
)


class TestWebSearch:
    @pytest.mark.asyncio
    async def test_empty_query(self):
        result = await web_search({"query": ""})
        assert "Error" in result

    @pytest.mark.asyncio
    @patch("infrastructure.local_execution.tools.web_tools._DDGS_AVAILABLE", True)
    @patch("infrastructure.local_execution.tools.web_tools.DDGS")
    async def test_search_via_ddgs(self, mock_ddgs_cls):
        mock_ddgs = MagicMock()
        mock_ddgs.text.return_value = [
            {"title": "Example Title", "href": "https://example.com", "body": "This is a snippet"},
            {"title": "Other Title", "href": "https://other.com", "body": "Another snippet"},
        ]
        mock_ddgs_cls.return_value = mock_ddgs

        result = await web_search({"query": "test", "max_results": 5})

        assert "Example Title" in result
        assert "https://example.com" in result
        assert "This is a snippet" in result
        mock_ddgs.text.assert_called_once_with("test", max_results=5)

    @pytest.mark.asyncio
    @patch("infrastructure.local_execution.tools.web_tools._DDGS_AVAILABLE", True)
    @patch("infrastructure.local_execution.tools.web_tools.DDGS")
    async def test_ddgs_no_results(self, mock_ddgs_cls):
        mock_ddgs = MagicMock()
        mock_ddgs.text.return_value = []
        mock_ddgs_cls.return_value = mock_ddgs

        result = await web_search({"query": "obscure query"})
        assert "No results found." in result

    @pytest.mark.asyncio
    @patch("infrastructure.local_execution.tools.web_tools._DDGS_AVAILABLE", False)
    @patch("infrastructure.local_execution.tools.web_tools.httpx.AsyncClient")
    async def test_html_fallback_when_ddgs_unavailable(self, mock_client_cls):
        html_response = """
        <div class="result">
            <a class="result__a" href="https://example.com">Example Title</a>
            <a class="result__snippet">This is a snippet</a>
        </div>
        """
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.text = html_response
        mock_resp.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_cls.return_value = mock_client

        result = await web_search({"query": "test", "max_results": 5})

        assert "Example Title" in result
        assert "https://example.com" in result

    @pytest.mark.asyncio
    @patch("infrastructure.local_execution.tools.web_tools._DDGS_AVAILABLE", True)
    @patch("infrastructure.local_execution.tools.web_tools.httpx.AsyncClient")
    @patch("infrastructure.local_execution.tools.web_tools.DDGS")
    async def test_ddgs_failure_falls_back_to_html(self, mock_ddgs_cls, mock_client_cls):
        # ddgs raises an error
        mock_ddgs = MagicMock()
        mock_ddgs.text.side_effect = RuntimeError("rate limited")
        mock_ddgs_cls.return_value = mock_ddgs

        # HTML fallback succeeds
        html_response = '<a class="result__a" href="https://fb.com">Fallback</a>'
        mock_resp = AsyncMock()
        mock_resp.text = html_response
        mock_resp.raise_for_status = lambda: None
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_cls.return_value = mock_client

        result = await web_search({"query": "test"})
        assert "Fallback" in result

    @pytest.mark.asyncio
    @patch("infrastructure.local_execution.tools.web_tools._DDGS_AVAILABLE", False)
    @patch("infrastructure.local_execution.tools.web_tools.httpx.AsyncClient")
    async def test_all_search_methods_fail(self, mock_client_cls):
        import httpx

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await web_search({"query": "test"})
        assert "Search error" in result


class TestWebFetch:
    @pytest.mark.asyncio
    async def test_empty_url(self):
        result = await web_fetch({"url": ""})
        assert "Error" in result

    @pytest.mark.asyncio
    @patch("infrastructure.local_execution.tools.web_tools.httpx.AsyncClient")
    async def test_fetch_html(self, mock_client_cls):
        mock_resp = AsyncMock()
        mock_resp.text = "<html><body><p>Hello world</p></body></html>"
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_cls.return_value = mock_client

        result = await web_fetch({"url": "https://example.com"})
        assert "Hello world" in result

    @pytest.mark.asyncio
    @patch("infrastructure.local_execution.tools.web_tools.httpx.AsyncClient")
    async def test_fetch_truncation(self, mock_client_cls):
        mock_resp = AsyncMock()
        mock_resp.text = "x" * 100
        mock_resp.headers = {"content-type": "text/plain"}
        mock_resp.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_cls.return_value = mock_client

        result = await web_fetch({"url": "https://example.com", "max_length": 50})
        assert "[truncated]" in result

    @pytest.mark.asyncio
    @patch("infrastructure.local_execution.tools.web_tools.httpx.AsyncClient")
    async def test_fetch_http_error(self, mock_client_cls):
        import httpx

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await web_fetch({"url": "https://example.com"})
        assert "Fetch error" in result


class TestHTMLParsing:
    def test_strip_html(self):
        assert _strip_html("<b>bold</b>") == "bold"
        assert _strip_html("no tags") == "no tags"
        assert _strip_html("&amp; &lt;") == "& <"

    def test_html_to_text_removes_scripts(self):
        html = "<script>alert('xss')</script><p>Hello</p>"
        text = _html_to_text(html)
        assert "alert" not in text
        assert "Hello" in text

    def test_html_to_text_removes_styles(self):
        html = "<style>body { color: red; }</style><p>Content</p>"
        text = _html_to_text(html)
        assert "color" not in text
        assert "Content" in text

    def test_parse_ddg_results_no_results(self):
        result = _parse_ddg_results("<html></html>", 5)
        assert result == "No results found."

    def test_parse_ddg_results_with_results(self):
        html = """
        <a class="result__a" href="https://a.com">Title A</a>
        <a class="result__snippet">Snippet A</a>
        """
        result = _parse_ddg_results(html, 5)
        assert "Title A" in result
        assert "https://a.com" in result
        assert "Snippet A" in result

    def test_parse_ddg_results_max_limit(self):
        html = """
        <a class="result__a" href="https://a.com">A</a>
        <a class="result__snippet">SA</a>
        <a class="result__a" href="https://b.com">B</a>
        <a class="result__snippet">SB</a>
        <a class="result__a" href="https://c.com">C</a>
        <a class="result__snippet">SC</a>
        """
        result = _parse_ddg_results(html, 2)
        assert "A" in result
        assert "B" in result
        assert "C" not in result or result.count("URL:") == 2
