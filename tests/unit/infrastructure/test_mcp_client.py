"""Tests for infrastructure/mcp/client.py — MCPClient, MCPToolAdapter, discover_and_register.

Unit tests with mocked MCP SDK internals (no real subprocesses).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.ports.mcp_client import MCPClientPort
from infrastructure.mcp.client import (
    MCPClient,
    MCPResourceSpec,
    MCPToolAdapter,
    MCPToolSpec,
    _ServerConnection,
    discover_and_register,
)

# ── MCPClientPort ABC ──


class TestMCPClientPort:
    def test_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            MCPClientPort()  # type: ignore[abstract]

    def test_mcpclient_implements_port(self) -> None:
        assert issubclass(MCPClient, MCPClientPort)


# ── MCPToolSpec / MCPResourceSpec ──


class TestSpecs:
    def test_tool_spec_frozen(self) -> None:
        spec = MCPToolSpec(server_name="s", name="t", description="d", input_schema={})
        with pytest.raises(AttributeError):
            spec.name = "other"  # type: ignore[misc]

    def test_resource_spec_frozen(self) -> None:
        spec = MCPResourceSpec(server_name="s", uri="u://x", name="n", description="d")
        with pytest.raises(AttributeError):
            spec.uri = "other"  # type: ignore[misc]


# ── MCPClient — connection management ──


class TestMCPClientConnection:
    def test_initial_state(self) -> None:
        client = MCPClient()
        assert client.connected_servers == []

    def test_disconnect_unknown_is_noop(self) -> None:
        client = MCPClient()
        # Should not raise
        import asyncio

        asyncio.run(client.disconnect("nonexistent"))

    def test_get_connection_raises_when_not_connected(self) -> None:
        client = MCPClient()
        with pytest.raises(ConnectionError, match="not connected"):
            client._get_connection("unknown")


# ── MCPClient — with mock session ──


def _make_connected_client(server_name: str = "test") -> MCPClient:
    """Create an MCPClient with a mocked connection."""
    client = MCPClient()
    mock_session = AsyncMock()
    conn = _ServerConnection(
        name=server_name,
        command="echo",
        args=[],
        session=mock_session,
    )
    client._connections[server_name] = conn
    return client


class TestMCPClientListTools:
    @pytest.mark.asyncio()
    async def test_list_tools_delegates(self) -> None:
        client = _make_connected_client()
        mock_tool = MagicMock()
        mock_tool.name = "my_tool"
        mock_tool.description = "does stuff"
        mock_tool.inputSchema = {"type": "object"}
        client._connections["test"].session.list_tools.return_value = MagicMock(tools=[mock_tool])
        tools = await client.list_tools("test")
        assert len(tools) == 1
        assert tools[0]["name"] == "my_tool"
        assert tools[0]["description"] == "does stuff"

    @pytest.mark.asyncio()
    async def test_list_tools_empty(self) -> None:
        client = _make_connected_client()
        client._connections["test"].session.list_tools.return_value = MagicMock(tools=[])
        tools = await client.list_tools("test")
        assert tools == []


class TestMCPClientCallTool:
    @pytest.mark.asyncio()
    async def test_call_tool_returns_text(self) -> None:
        client = _make_connected_client()
        mock_content = MagicMock()
        mock_content.text = "tool result"
        client._connections["test"].session.call_tool.return_value = MagicMock(
            content=[mock_content]
        )
        result = await client.call_tool("test", "my_tool", {"arg": "value"})
        assert result == "tool result"

    @pytest.mark.asyncio()
    async def test_call_tool_empty_result(self) -> None:
        client = _make_connected_client()
        client._connections["test"].session.call_tool.return_value = MagicMock(content=[])
        result = await client.call_tool("test", "my_tool")
        assert result == ""


class TestMCPClientListResources:
    @pytest.mark.asyncio()
    async def test_list_resources(self) -> None:
        client = _make_connected_client()
        mock_resource = MagicMock()
        mock_resource.uri = "file://test.txt"
        mock_resource.name = "test"
        mock_resource.description = "test file"
        client._connections["test"].session.list_resources.return_value = MagicMock(
            resources=[mock_resource]
        )
        resources = await client.list_resources("test")
        assert len(resources) == 1
        assert resources[0]["uri"] == "file://test.txt"


class TestMCPClientReadResource:
    @pytest.mark.asyncio()
    async def test_read_resource(self) -> None:
        client = _make_connected_client()
        mock_content = MagicMock()
        mock_content.text = "file contents"
        client._connections["test"].session.read_resource.return_value = MagicMock(
            contents=[mock_content]
        )
        result = await client.read_resource("test", "file://test.txt")
        assert result == "file contents"

    @pytest.mark.asyncio()
    async def test_read_resource_empty(self) -> None:
        client = _make_connected_client()
        client._connections["test"].session.read_resource.return_value = MagicMock(contents=[])
        result = await client.read_resource("test", "file://empty.txt")
        assert result == ""


# ── MCPClient — disconnect ──


class TestMCPClientDisconnect:
    @pytest.mark.asyncio()
    async def test_disconnect_removes_connection(self) -> None:
        client = _make_connected_client()
        assert "test" in client._connections
        await client.disconnect("test")
        assert "test" not in client._connections

    @pytest.mark.asyncio()
    async def test_disconnect_all(self) -> None:
        client = _make_connected_client("server1")
        conn2 = _ServerConnection(name="server2", command="echo", args=[], session=AsyncMock())
        client._connections["server2"] = conn2
        assert len(client.connected_servers) == 2
        await client.disconnect_all()
        assert client.connected_servers == []


# ── MCPToolAdapter ──


class TestMCPToolAdapter:
    def test_name_prefixed(self) -> None:
        client = _make_connected_client("myserver")
        adapter = MCPToolAdapter(client, "myserver", "my_tool")
        assert adapter.name == "mcp_myserver_my_tool"

    @pytest.mark.asyncio()
    async def test_call_delegates_to_client(self) -> None:
        client = _make_connected_client()
        mock_content = MagicMock()
        mock_content.text = "adapter result"
        client._connections["test"].session.call_tool.return_value = MagicMock(
            content=[mock_content]
        )
        adapter = MCPToolAdapter(client, "test", "some_tool")
        result = await adapter(arg1="val1")
        assert result == "adapter result"
        client._connections["test"].session.call_tool.assert_called_once_with(
            "some_tool", arguments={"arg1": "val1"}
        )


# ── discover_and_register ──


class TestDiscoverAndRegister:
    @pytest.mark.asyncio()
    async def test_empty_configs(self) -> None:
        client = MCPClient()
        adapters = await discover_and_register(client, [])
        assert adapters == []

    @pytest.mark.asyncio()
    async def test_failed_connection_skips(self) -> None:
        client = MCPClient()
        configs = [{"name": "bad", "command": "nonexistent_cmd_xyz"}]
        # Should not raise, just log warning
        adapters = await discover_and_register(client, configs)
        assert adapters == []

    @pytest.mark.asyncio()
    async def test_discover_creates_adapters(self) -> None:
        client = MCPClient()
        # Pre-wire a mock connection
        mock_session = AsyncMock()
        mock_tool1 = MagicMock()
        mock_tool1.name = "tool1"
        mock_tool1.description = "desc1"
        mock_tool1.inputSchema = {}
        mock_tool2 = MagicMock()
        mock_tool2.name = "tool2"
        mock_tool2.description = "desc2"
        mock_tool2.inputSchema = {}
        mock_session.list_tools.return_value = MagicMock(tools=[mock_tool1, mock_tool2])

        # Patch connect to inject our mock session
        async def fake_connect(name: str, command: str, args: list | None = None) -> None:
            client._connections[name] = _ServerConnection(
                name=name, command=command, args=args or [], session=mock_session
            )

        client.connect = fake_connect  # type: ignore[assignment]

        configs = [{"name": "srv", "command": "echo", "args": []}]
        adapters = await discover_and_register(client, configs)
        assert len(adapters) == 2
        assert adapters[0].name == "mcp_srv_tool1"
        assert adapters[1].name == "mcp_srv_tool2"
