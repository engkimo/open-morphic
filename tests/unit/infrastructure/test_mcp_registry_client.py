"""Tests for MCPRegistryClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from domain.services.tool_safety_scorer import ToolSafetyScorer
from domain.value_objects.tool_safety import SafetyTier
from infrastructure.marketplace.mcp_registry_client import MCPRegistryClient


@pytest.fixture
def scorer() -> ToolSafetyScorer:
    return ToolSafetyScorer()


@pytest.fixture
def client(scorer: ToolSafetyScorer) -> MCPRegistryClient:
    return MCPRegistryClient(safety_scorer=scorer, base_url="https://test.registry")


def _mock_response(status_code: int = 200, json_data: object = None) -> httpx.Response:
    """Create a mock httpx.Response."""
    resp = httpx.Response(
        status_code=status_code,
        json=json_data,
        request=httpx.Request("GET", "https://test.registry/api/servers"),
    )
    return resp


class TestMCPRegistryClient:
    async def test_search_returns_candidates(self, client: MCPRegistryClient) -> None:
        data = [
            {
                "name": "filesystem",
                "description": "Read and write files",
                "publisher": "modelcontextprotocol",
                "package_name": "@modelcontextprotocol/server-filesystem",
                "transport": "stdio",
                "source_url": "https://github.com/mcp/servers",
                "download_count": 15000,
            },
        ]
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _mock_response(200, data)
            result = await client.search("filesystem")

        assert result.total_count == 1
        assert result.candidates[0].name == "filesystem"
        assert result.candidates[0].safety_score > 0.0
        assert result.error is None

    async def test_search_with_dict_response(self, client: MCPRegistryClient) -> None:
        data = {"servers": [{"name": "github", "publisher": "github"}]}
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _mock_response(200, data)
            result = await client.search("github")

        assert result.total_count == 1
        assert result.candidates[0].name == "github"

    async def test_search_with_results_key(self, client: MCPRegistryClient) -> None:
        data = {"results": [{"name": "slack", "publisher": "slack"}]}
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _mock_response(200, data)
            result = await client.search("slack")

        assert result.total_count == 1

    async def test_search_respects_limit(self, client: MCPRegistryClient) -> None:
        data = [{"name": f"tool-{i}", "publisher": "dev"} for i in range(20)]
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _mock_response(200, data)
            result = await client.search("tools", limit=5)

        assert result.total_count == 5

    async def test_search_scores_candidates(self, client: MCPRegistryClient) -> None:
        data = [
            {"name": "fs", "publisher": "anthropic", "transport": "stdio"},
        ]
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _mock_response(200, data)
            result = await client.search("fs")

        assert result.candidates[0].safety_tier >= SafetyTier.COMMUNITY

    async def test_search_handles_http_error(self, client: MCPRegistryClient) -> None:
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _mock_response(500, {"error": "Internal"})
            result = await client.search("test")

        assert result.total_count == 0
        assert result.error == "HTTP 500"

    async def test_search_handles_connection_error(self, client: MCPRegistryClient) -> None:
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = httpx.ConnectError("Connection refused")
            result = await client.search("test")

        assert result.total_count == 0
        assert result.error is not None

    async def test_search_handles_timeout(self, client: MCPRegistryClient) -> None:
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = httpx.TimeoutException("Timed out")
            result = await client.search("test")

        assert result.total_count == 0
        assert result.error is not None

    async def test_search_handles_malformed_json(self, client: MCPRegistryClient) -> None:
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _mock_response(200, "not a list or dict")
            result = await client.search("test")

        assert result.total_count == 0

    async def test_parse_item_builds_npm_install_command(self, client: MCPRegistryClient) -> None:
        data = [{"name": "fs", "package_name": "@mcp/server-fs"}]
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _mock_response(200, data)
            result = await client.search("fs")

        assert result.candidates[0].install_command == "npx -y @mcp/server-fs"

    async def test_parse_item_builds_pip_install_command(self, client: MCPRegistryClient) -> None:
        data = [{"name": "pytools", "package_name": "mcp-pytools"}]
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _mock_response(200, data)
            result = await client.search("pytools")

        assert result.candidates[0].install_command == "pip install mcp-pytools"

    async def test_parse_item_uses_title_fallback(self, client: MCPRegistryClient) -> None:
        data = [{"title": "MyTool", "author": "dev"}]
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _mock_response(200, data)
            result = await client.search("tool")

        assert result.candidates[0].name == "MyTool"
        assert result.candidates[0].publisher == "dev"

    async def test_parse_item_skips_unparseable(self, client: MCPRegistryClient) -> None:
        data = [
            {"name": "good", "publisher": "dev"},
            None,  # unparseable
            42,  # unparseable
        ]
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _mock_response(200, data)
            result = await client.search("test")

        assert result.total_count == 1

    async def test_empty_search_results(self, client: MCPRegistryClient) -> None:
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _mock_response(200, [])
            result = await client.search("nonexistent")

        assert result.total_count == 0
        assert result.candidates == []
        assert result.error is None
