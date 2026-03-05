"""MCPRegistryClient — HTTP client for the MCP Registry.

Queries registry.modelcontextprotocol.io and returns scored ToolCandidate results.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from domain.entities.tool_candidate import ToolCandidate
from domain.ports.tool_registry import ToolRegistryPort, ToolSearchResult
from domain.services.tool_safety_scorer import ToolSafetyScorer

logger = logging.getLogger(__name__)

_DEFAULT_REGISTRY_URL = "https://registry.modelcontextprotocol.io"


class MCPRegistryClient(ToolRegistryPort):
    """Search the MCP Registry and return safety-scored candidates.

    All HTTP calls go through _request() for testability.
    Returns empty ToolSearchResult on any HTTP failure (never raises).
    """

    def __init__(
        self,
        safety_scorer: ToolSafetyScorer,
        base_url: str = _DEFAULT_REGISTRY_URL,
        timeout: float = 10.0,
    ) -> None:
        self._scorer = safety_scorer
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """HTTP request to MCP Registry."""
        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
        ) as client:
            func = getattr(client, method)
            return await func(path, **kwargs)

    async def search(self, query: str, limit: int = 10) -> ToolSearchResult:
        """Search MCP Registry for tools matching query."""
        try:
            resp = await self._request(
                "get",
                "/api/servers",
                params={"q": query, "limit": limit},
            )
            if resp.status_code != 200:
                logger.warning(
                    "MCP Registry returned %d for query '%s'",
                    resp.status_code,
                    query,
                )
                return ToolSearchResult(query=query, error=f"HTTP {resp.status_code}")

            data = resp.json()
            candidates = self._parse_response(data)
            scored = [self._scorer.score(c) for c in candidates[:limit]]

            return ToolSearchResult(
                query=query,
                candidates=scored,
                total_count=len(scored),
            )

        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.warning("MCP Registry unreachable: %s", exc)
            return ToolSearchResult(query=query, error=str(exc))
        except Exception as exc:
            logger.warning("MCP Registry search failed: %s", exc)
            return ToolSearchResult(query=query, error=str(exc))

    def _parse_response(self, data: Any) -> list[ToolCandidate]:
        """Parse registry JSON response into ToolCandidate list."""
        items: list[dict[str, Any]] = []

        # Handle both list and dict-with-servers formats
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("servers", data.get("results", []))

        candidates: list[ToolCandidate] = []
        for item in items:
            try:
                candidates.append(self._parse_item(item))
            except Exception:
                logger.debug("Skipping unparseable registry item: %s", item)
                continue

        return candidates

    def _parse_item(self, item: dict[str, Any]) -> ToolCandidate:
        """Parse a single registry item into a ToolCandidate."""
        name = item.get("name", item.get("title", ""))
        package_name = item.get("package_name", item.get("package", name))
        publisher = item.get("publisher", item.get("author", ""))

        # Build install command from package metadata
        install_command = item.get("install_command", "")
        if not install_command and package_name:
            if package_name.startswith("@") or package_name.startswith("npm:"):
                install_command = f"npx -y {package_name}"
            elif "/" not in package_name:
                install_command = f"pip install {package_name}"

        return ToolCandidate(
            name=name or "unknown",
            description=item.get("description", ""),
            publisher=publisher,
            package_name=package_name,
            transport=item.get("transport", "stdio"),
            install_command=install_command,
            source_url=item.get("source_url", item.get("url", item.get("repo", ""))),
            download_count=item.get("download_count", item.get("downloads", 0)),
        )
