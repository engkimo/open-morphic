"""Web tools — search and fetch for LAEE. API-key-free via DuckDuckGo."""

from __future__ import annotations

import asyncio
import html
import logging
import re
from typing import Any

import httpx

try:
    from ddgs import DDGS

    _DDGS_AVAILABLE = True
except ImportError:
    _DDGS_AVAILABLE = False

logger = logging.getLogger(__name__)

_TIMEOUT = 15.0
_MAX_FETCH_CHARS = 20_000
_DDG_URL = "https://html.duckduckgo.com/html/"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)


async def web_search(args: dict[str, Any]) -> str:
    """Search the web via DuckDuckGo (no API key needed).

    Args:
        query: Search query string.
        max_results: Maximum results to return (default 5).
    """
    query = args.get("query", "")
    max_results = args.get("max_results", 5)
    if not query:
        return "Error: query is required"

    # Primary: ddgs package (reliable, handles anti-bot)
    if _DDGS_AVAILABLE:
        try:
            return await _ddgs_search(query, max_results)
        except Exception as exc:
            logger.warning("ddgs search failed, trying HTML fallback: %s", exc)

    # Fallback: raw HTML scraping (may fail due to bot detection)
    try:
        return await _ddg_html_search(query, max_results)
    except Exception as exc:
        return f"Search error: {exc}"


async def _ddgs_search(query: str, max_results: int) -> str:
    """Search via ddgs package (sync, run in thread pool)."""

    def _search() -> list[dict[str, str]]:
        return DDGS().text(query, max_results=max_results)

    results = await asyncio.to_thread(_search)
    if not results:
        return "No results found."

    formatted = []
    for i, r in enumerate(results):
        formatted.append(f"{i + 1}. {r['title']}\n   URL: {r['href']}\n   {r['body']}")
    return "\n\n".join(formatted)


async def _ddg_html_search(query: str, max_results: int) -> str:
    """Fallback: search via DuckDuckGo HTML endpoint."""
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        resp = await client.post(
            _DDG_URL,
            data={"q": query, "b": ""},
            headers={"User-Agent": _USER_AGENT},
        )
        resp.raise_for_status()
        return _parse_ddg_results(resp.text, max_results)


def _parse_ddg_results(html_content: str, max_results: int) -> str:
    """Parse DuckDuckGo HTML response into structured text."""
    link_pattern = re.compile(
        r'<a\s+[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'<a\s+[^>]*class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL,
    )

    links = link_pattern.findall(html_content)
    snippets = snippet_pattern.findall(html_content)

    if not links:
        return "No results found."

    results = []
    for i, (url, title) in enumerate(links[:max_results]):
        clean_title = _strip_html(title).strip()
        clean_url = html.unescape(url)
        snippet = _strip_html(snippets[i]).strip() if i < len(snippets) else ""
        results.append(f"{i + 1}. {clean_title}\n   URL: {clean_url}\n   {snippet}")

    return "\n\n".join(results)


async def web_fetch(args: dict[str, Any]) -> str:
    """Fetch a URL and return its text content (HTML tags stripped).

    Args:
        url: The URL to fetch.
        max_length: Maximum characters to return (default 20000).
    """
    url = args.get("url", "")
    max_length = args.get("max_length", _MAX_FETCH_CHARS)
    if not url:
        return "Error: url is required"

    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT, follow_redirects=True, max_redirects=5
        ) as client:
            resp = await client.get(url, headers={"User-Agent": _USER_AGENT})
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            text = _html_to_text(resp.text) if "text/html" in content_type else resp.text

            if len(text) > max_length:
                text = text[:max_length] + "\n... [truncated]"
            return text
    except httpx.HTTPError as e:
        return f"Fetch error: {e}"


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    clean = re.sub(r"<[^>]+>", "", text)
    return html.unescape(clean)


def _html_to_text(raw_html: str) -> str:
    """Convert HTML to readable text by stripping tags and normalizing whitespace."""
    text = re.sub(r"<script[^>]*>.*?</script>", "", raw_html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<(?:br|p|div|h[1-6]|li|tr)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = _strip_html(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
