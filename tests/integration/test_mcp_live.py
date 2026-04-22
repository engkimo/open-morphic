"""MCP Live E2E integration tests — Sprint 19.1 (Round 12).

Tests the full MCP pipeline with a real mcp-server-fetch process:
  MCPClient connect → list_tools → call_tool → ReactExecutor routing → disconnect.

Requires: uvx mcp-server-fetch (auto-skipped if unavailable).

Run:
    uv run pytest tests/integration/test_mcp_live.py -v -s
"""

from __future__ import annotations

import shutil
from unittest.mock import AsyncMock

import pytest

from infrastructure.mcp.client import MCPClient, MCPToolAdapter, discover_and_register
from infrastructure.task_graph.react_executor import ReactExecutor

# ---------------------------------------------------------------------------
# Skip if uvx not available
# ---------------------------------------------------------------------------

_HAS_UVX = shutil.which("uvx") is not None


def _skip_no_uvx() -> pytest.MarkDecorator:
    return pytest.mark.skipif(not _HAS_UVX, reason="uvx not installed")


pytestmark = [
    pytest.mark.asyncio,
    _skip_no_uvx(),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SERVER_NAME = "fetch"
SERVER_COMMAND = "uvx"
SERVER_ARGS = ["mcp-server-fetch"]


@pytest.fixture
async def mcp_client():
    """Create and connect an MCPClient to mcp-server-fetch."""
    client = MCPClient()
    await client.connect(SERVER_NAME, SERVER_COMMAND, SERVER_ARGS)
    yield client
    await client.disconnect_all()


# ===========================================================================
# Test 1: Connection lifecycle
# ===========================================================================


async def test_connect_and_list_servers(mcp_client: MCPClient) -> None:
    """MCPClient connects to mcp-server-fetch and reports it as connected."""
    assert SERVER_NAME in mcp_client.connected_servers


# ===========================================================================
# Test 2: Tool discovery
# ===========================================================================


async def test_list_tools_returns_fetch_tool(mcp_client: MCPClient) -> None:
    """mcp-server-fetch exposes at least one tool with an input schema."""
    tools = await mcp_client.list_tools(SERVER_NAME)
    assert len(tools) >= 1

    # The fetch tool should have a name and input schema
    tool = tools[0]
    assert "name" in tool
    assert isinstance(tool["name"], str)
    assert len(tool["name"]) > 0
    # inputSchema should exist (may be dict or empty)
    assert "inputSchema" in tool or "description" in tool


# ===========================================================================
# Test 3: Tool call — fetch a known URL
# ===========================================================================


async def test_call_fetch_tool(mcp_client: MCPClient) -> None:
    """Call the fetch tool with https://example.com and verify content returned."""
    tools = await mcp_client.list_tools(SERVER_NAME)
    tool_name = tools[0]["name"]

    result = await mcp_client.call_tool(
        SERVER_NAME,
        tool_name,
        {"url": "https://example.com"},
    )

    # example.com returns a page with "Example Domain" in the content
    assert isinstance(result, str)
    assert len(result) > 50, f"Result too short ({len(result)} chars): {result[:100]}"
    assert "Example Domain" in result or "example" in result.lower()


# ===========================================================================
# Test 4: MCPToolAdapter wraps tool correctly
# ===========================================================================


async def test_mcp_tool_adapter(mcp_client: MCPClient) -> None:
    """MCPToolAdapter adapts an MCP tool into a callable."""
    tools = await mcp_client.list_tools(SERVER_NAME)
    tool_name = tools[0]["name"]

    adapter = MCPToolAdapter(mcp_client, SERVER_NAME, tool_name)
    assert adapter.name == f"mcp_{SERVER_NAME}_{tool_name}"

    result = await adapter(url="https://example.com")
    assert isinstance(result, str)
    assert len(result) > 50


# ===========================================================================
# Test 5: discover_and_register batch connects
# ===========================================================================


async def test_discover_and_register() -> None:
    """discover_and_register connects and creates adapters."""
    client = MCPClient()
    try:
        configs = [{"name": SERVER_NAME, "command": SERVER_COMMAND, "args": SERVER_ARGS}]
        adapters = await discover_and_register(client, configs)

        assert len(adapters) >= 1
        assert SERVER_NAME in client.connected_servers
        assert all(isinstance(a, MCPToolAdapter) for a in adapters)
    finally:
        await client.disconnect_all()


# ===========================================================================
# Test 6: ReactExecutor registers MCP tools and routes correctly
# ===========================================================================


async def test_react_executor_mcp_tool_registration(mcp_client: MCPClient) -> None:
    """ReactExecutor.register_mcp_tools adds MCP tool schemas."""
    tools = await mcp_client.list_tools(SERVER_NAME)

    react = ReactExecutor(
        llm=AsyncMock(),
        executor=AsyncMock(),
        tool_schemas=[],
        mcp_client=mcp_client,
    )

    react.register_mcp_tools(SERVER_NAME, tools)

    assert react.mcp_tool_count >= 1
    assert react.laee_tool_count == 0
    # Tool names tracked for routing
    tool_name = tools[0]["name"]
    assert tool_name in react._mcp_tool_names
    assert react._mcp_tool_server[tool_name] == SERVER_NAME


# ===========================================================================
# Test 7: Full MCP tool routing through ReactExecutor._execute_tool
# ===========================================================================


async def test_react_executor_routes_mcp_tool_call(mcp_client: MCPClient) -> None:
    """ReactExecutor routes MCP tool calls to MCPClient, not LAEE."""
    tools = await mcp_client.list_tools(SERVER_NAME)
    tool_name = tools[0]["name"]

    mock_executor = AsyncMock()
    react = ReactExecutor(
        llm=AsyncMock(),
        executor=mock_executor,
        tool_schemas=[],
        mcp_client=mcp_client,
    )
    react.register_mcp_tools(SERVER_NAME, tools)

    # Simulate a tool call result from LLM
    from domain.ports.llm_gateway import ToolCallResult

    tc = ToolCallResult(
        id="tc-1",
        tool_name=tool_name,
        arguments={"url": "https://example.com"},
    )

    result = await react._execute_tool(tc)

    # Should have fetched content via MCP, not LAEE
    assert isinstance(result, str)
    assert len(result) > 50
    # LAEE executor should NOT have been called
    mock_executor.execute.assert_not_called()


# ===========================================================================
# Test 8: Disconnect cleans up
# ===========================================================================


async def test_disconnect_removes_server() -> None:
    """After disconnect, server is no longer in connected_servers."""
    client = MCPClient()
    await client.connect(SERVER_NAME, SERVER_COMMAND, SERVER_ARGS)
    assert SERVER_NAME in client.connected_servers

    await client.disconnect(SERVER_NAME)
    assert SERVER_NAME not in client.connected_servers


# ===========================================================================
# Test 9: Schema conversion produces valid OpenAI function format
# ===========================================================================


async def test_mcp_to_openai_schema_format(mcp_client: MCPClient) -> None:
    """Registered MCP schemas follow OpenAI function-calling format."""
    tools = await mcp_client.list_tools(SERVER_NAME)

    react = ReactExecutor(
        llm=AsyncMock(),
        executor=AsyncMock(),
        tool_schemas=[],
        mcp_client=mcp_client,
    )
    react.register_mcp_tools(SERVER_NAME, tools)

    for schema in react._schemas:
        assert schema["type"] == "function"
        fn = schema["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn
        assert fn["parameters"].get("type") == "object"


# ===========================================================================
# Test 10: Startup flow mirrors container._connect_mcp_servers
# ===========================================================================


async def test_full_startup_flow() -> None:
    """Simulate container startup: connect → list → register → verify counts."""
    import json

    mcp_servers_json = json.dumps(
        [{"name": SERVER_NAME, "command": SERVER_COMMAND, "args": SERVER_ARGS}]
    )
    server_configs = json.loads(mcp_servers_json)

    client = MCPClient()
    react = ReactExecutor(
        llm=AsyncMock(),
        executor=AsyncMock(),
        tool_schemas=[{"type": "function", "function": {"name": "shell_exec"}}],
        mcp_client=client,
    )

    try:
        for cfg in server_configs:
            await client.connect(cfg["name"], cfg["command"], cfg.get("args", []))
            tools = await client.list_tools(cfg["name"])
            react.register_mcp_tools(cfg["name"], tools)

        # Verify tool availability (mirrors startup log)
        laee_count = react.laee_tool_count
        mcp_count = react.mcp_tool_count
        total = laee_count + mcp_count

        assert laee_count == 1  # shell_exec
        assert mcp_count >= 1  # fetch tool(s)
        assert total >= 2

    finally:
        await client.disconnect_all()
