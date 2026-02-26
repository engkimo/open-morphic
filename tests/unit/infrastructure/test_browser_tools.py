"""Tests for browser tools — Sprint 2-E. All mocked, no real Playwright."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from infrastructure.local_execution.tools import browser_tools


@pytest.fixture(autouse=True)
def _reset_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the lazy browser singleton between tests."""
    monkeypatch.setattr(browser_tools, "_browser", None)


def _mock_page(title: str = "Test Page", status: int = 200, text: str = "page content") -> AsyncMock:
    """Create a mock Playwright page."""
    page = AsyncMock()
    page.title = AsyncMock(return_value=title)
    page.close = AsyncMock()

    response = MagicMock()
    response.status = status
    page.goto = AsyncMock(return_value=response)

    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.screenshot = AsyncMock()
    page.pdf = AsyncMock()

    element = AsyncMock()
    element.text_content = AsyncMock(return_value=text)
    page.query_selector = AsyncMock(return_value=element)

    return page


class TestBrowserNavigate:
    @pytest.mark.asyncio
    async def test_navigate_returns_title_and_status(self) -> None:
        page = _mock_page(title="Example", status=200)
        with patch.object(browser_tools, "_get_page", return_value=page):
            result = await browser_tools.browser_navigate({"url": "https://example.com"})
        assert "Example" in result
        assert "200" in result

    @pytest.mark.asyncio
    async def test_navigate_empty_url_raises(self) -> None:
        with pytest.raises(ValueError, match="url is required"):
            await browser_tools.browser_navigate({})

    @pytest.mark.asyncio
    async def test_navigate_closes_page(self) -> None:
        page = _mock_page()
        with patch.object(browser_tools, "_get_page", return_value=page):
            await browser_tools.browser_navigate({"url": "https://test.com"})
        page.close.assert_awaited_once()


class TestBrowserClick:
    @pytest.mark.asyncio
    async def test_click_by_selector(self) -> None:
        page = _mock_page()
        with patch.object(browser_tools, "_get_page", return_value=page):
            result = await browser_tools.browser_click({"selector": "button.submit"})
        assert "button.submit" in result
        page.click.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_click_empty_selector_raises(self) -> None:
        with pytest.raises(ValueError, match="selector is required"):
            await browser_tools.browser_click({})


class TestBrowserType:
    @pytest.mark.asyncio
    async def test_type_text(self) -> None:
        page = _mock_page()
        with patch.object(browser_tools, "_get_page", return_value=page):
            result = await browser_tools.browser_type(
                {"selector": "#email", "text": "test@example.com"}
            )
        assert "test@example.com" in result
        page.fill.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_type_missing_args_raises(self) -> None:
        with pytest.raises(ValueError):
            await browser_tools.browser_type({"selector": "#email"})


class TestBrowserScreenshot:
    @pytest.mark.asyncio
    async def test_screenshot_saved(self) -> None:
        page = _mock_page()
        with patch.object(browser_tools, "_get_page", return_value=page):
            result = await browser_tools.browser_screenshot(
                {"url": "https://example.com", "path": "/tmp/test.png"}
            )
        assert "/tmp/test.png" in result
        page.screenshot.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_screenshot_no_url_raises(self) -> None:
        with pytest.raises(ValueError, match="url is required"):
            await browser_tools.browser_screenshot({"path": "/tmp/test.png"})


class TestBrowserExtract:
    @pytest.mark.asyncio
    async def test_extract_text(self) -> None:
        page = _mock_page(text="Hello World")
        with patch.object(browser_tools, "_get_page", return_value=page):
            result = await browser_tools.browser_extract(
                {"url": "https://example.com", "selector": "h1"}
            )
        assert result == "Hello World"

    @pytest.mark.asyncio
    async def test_extract_no_element(self) -> None:
        page = _mock_page()
        page.query_selector = AsyncMock(return_value=None)
        with patch.object(browser_tools, "_get_page", return_value=page):
            result = await browser_tools.browser_extract(
                {"url": "https://example.com", "selector": ".missing"}
            )
        assert "No element found" in result


class TestBrowserPdf:
    @pytest.mark.asyncio
    async def test_pdf_saved(self) -> None:
        page = _mock_page()
        with patch.object(browser_tools, "_get_page", return_value=page):
            result = await browser_tools.browser_pdf(
                {"url": "https://example.com", "path": "/tmp/test.pdf"}
            )
        assert "/tmp/test.pdf" in result
        page.pdf.assert_awaited_once()


class TestToolRegistration:
    def test_browser_tools_in_registry(self) -> None:
        from infrastructure.local_execution.tools import TOOL_REGISTRY

        browser_tools_names = [
            "browser_navigate", "browser_click", "browser_type",
            "browser_screenshot", "browser_extract", "browser_pdf",
        ]
        for name in browser_tools_names:
            assert name in TOOL_REGISTRY, f"{name} not in TOOL_REGISTRY"
