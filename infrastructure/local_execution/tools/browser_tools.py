"""Browser tools — Playwright automation for LAEE."""

from __future__ import annotations

import asyncio
from typing import Any

# Lazy singleton to reuse Playwright browser instance
_browser = None
_browser_lock = asyncio.Lock()


async def _get_browser():  # noqa: ANN202
    """Lazy-init a Playwright browser instance."""
    global _browser  # noqa: PLW0603
    async with _browser_lock:
        if _browser is None:
            from playwright.async_api import async_playwright

            pw = await async_playwright().start()
            _browser = await pw.chromium.launch(headless=True)
        return _browser


async def _get_page():  # noqa: ANN202
    """Get a new page from the shared browser."""
    browser = await _get_browser()
    return await browser.new_page()


async def browser_navigate(args: dict[str, Any]) -> str:
    """Navigate to a URL, return page title and status."""
    url = args.get("url", "")
    if not url:
        raise ValueError("url is required")

    page = await _get_page()
    try:
        response = await page.goto(url, timeout=args.get("timeout", 30000))
        title = await page.title()
        status = response.status if response else "unknown"
        return f"Navigated to {url} | Title: {title} | Status: {status}"
    finally:
        await page.close()


async def browser_click(args: dict[str, Any]) -> str:
    """Click an element by CSS selector."""
    url = args.get("url", "")
    selector = args.get("selector", "")
    if not selector:
        raise ValueError("selector is required")

    page = await _get_page()
    try:
        if url:
            await page.goto(url, timeout=30000)
        await page.click(selector, timeout=args.get("timeout", 5000))
        return f"Clicked element: {selector}"
    finally:
        await page.close()


async def browser_type(args: dict[str, Any]) -> str:
    """Type text into an element by CSS selector."""
    url = args.get("url", "")
    selector = args.get("selector", "")
    text = args.get("text", "")
    if not selector or not text:
        raise ValueError("selector and text are required")

    page = await _get_page()
    try:
        if url:
            await page.goto(url, timeout=30000)
        await page.fill(selector, text, timeout=args.get("timeout", 5000))
        return f"Typed '{text}' into {selector}"
    finally:
        await page.close()


async def browser_screenshot(args: dict[str, Any]) -> str:
    """Capture a screenshot of a page."""
    url = args.get("url", "")
    path = args.get("path", "screenshot.png")
    if not url:
        raise ValueError("url is required")

    page = await _get_page()
    try:
        await page.goto(url, timeout=30000)
        await page.screenshot(path=path, full_page=args.get("full_page", False))
        return f"Screenshot saved to {path}"
    finally:
        await page.close()


async def browser_extract(args: dict[str, Any]) -> str:
    """Extract text or HTML from a page element."""
    url = args.get("url", "")
    selector = args.get("selector", "body")

    page = await _get_page()
    try:
        if url:
            await page.goto(url, timeout=30000)
        element = await page.query_selector(selector)
        if element is None:
            return f"No element found for selector: {selector}"
        text = await element.text_content()
        return text or ""
    finally:
        await page.close()


async def browser_pdf(args: dict[str, Any]) -> str:
    """Save a page as PDF."""
    url = args.get("url", "")
    path = args.get("path", "page.pdf")
    if not url:
        raise ValueError("url is required")

    page = await _get_page()
    try:
        await page.goto(url, timeout=30000)
        await page.pdf(path=path)
        return f"PDF saved to {path}"
    finally:
        await page.close()
