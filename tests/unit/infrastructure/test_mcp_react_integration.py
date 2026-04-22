"""Tests for MCP ↔ ReactExecutor integration (Sprint 18.1).

Covers:
- register_mcp_tools() schema conversion and tool tracking
- Container _connect_mcp_servers() startup flow
- Public mcp_client / tool count properties
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from infrastructure.task_graph.react_executor import ReactExecutor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_react(
    schemas: list[dict[str, Any]] | None = None,
    mcp_client: Any | None = None,
    mcp_tool_names: set[str] | None = None,
) -> ReactExecutor:
    """Build a ReactExecutor with mocked dependencies."""
    return ReactExecutor(
        llm=AsyncMock(),
        executor=AsyncMock(),
        tool_schemas=schemas or [],
        mcp_client=mcp_client,
        mcp_tool_names=mcp_tool_names,
    )


def _mcp_tool_desc(
    name: str,
    description: str = "A tool",
    input_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an MCP tool description dict."""
    d: dict[str, Any] = {"name": name, "description": description}
    if input_schema is not None:
        d["inputSchema"] = input_schema
    return d


# ===========================================================================
# TestRegisterMCPTools — schema conversion, tracking, edge cases
# ===========================================================================


class TestRegisterMCPTools:
    """register_mcp_tools() converts MCP → OpenAI format and tracks routing."""

    def test_basic_schema_conversion(self) -> None:
        """MCP tool description → OpenAI function-calling schema."""
        react = _make_react()
        input_schema = {
            "type": "object",
            "properties": {"url": {"type": "string"}},
        }
        tools = [_mcp_tool_desc("fetch", "Fetch a URL", input_schema)]

        react.register_mcp_tools("fetch-server", tools)

        assert len(react._schemas) == 1
        schema = react._schemas[0]
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "fetch"
        assert schema["function"]["description"] == "Fetch a URL"
        assert schema["function"]["parameters"]["properties"]["url"]["type"] == "string"

    def test_tool_name_tracked(self) -> None:
        """Registered tool names appear in _mcp_tool_names."""
        react = _make_react()
        react.register_mcp_tools("srv", [_mcp_tool_desc("alpha"), _mcp_tool_desc("beta")])

        assert react._mcp_tool_names == {"alpha", "beta"}

    def test_tool_server_mapping(self) -> None:
        """Each tool maps back to its server name."""
        react = _make_react()
        react.register_mcp_tools("brave", [_mcp_tool_desc("brave_search")])

        assert react._mcp_tool_server["brave_search"] == "brave"

    def test_multiple_servers(self) -> None:
        """Tools from multiple servers coexist."""
        react = _make_react()
        react.register_mcp_tools("srv-a", [_mcp_tool_desc("tool_a")])
        react.register_mcp_tools("srv-b", [_mcp_tool_desc("tool_b")])

        assert react._mcp_tool_names == {"tool_a", "tool_b"}
        assert react._mcp_tool_server["tool_a"] == "srv-a"
        assert react._mcp_tool_server["tool_b"] == "srv-b"
        assert len(react._schemas) == 2

    def test_empty_name_skipped(self) -> None:
        """Tool descriptions with empty name are silently skipped."""
        react = _make_react()
        react.register_mcp_tools(
            "srv",
            [{"name": "", "description": "skip me"}, _mcp_tool_desc("valid")],
        )

        assert react._mcp_tool_names == {"valid"}
        assert len(react._schemas) == 1

    def test_missing_name_skipped(self) -> None:
        """Tool descriptions without name key are skipped."""
        react = _make_react()
        react.register_mcp_tools("srv", [{"description": "no name"}, _mcp_tool_desc("ok")])

        assert react._mcp_tool_names == {"ok"}

    def test_missing_input_schema_defaults(self) -> None:
        """When inputSchema is absent, default empty object is used."""
        react = _make_react()
        react.register_mcp_tools("srv", [_mcp_tool_desc("tool_x")])

        params = react._schemas[0]["function"]["parameters"]
        assert params == {"type": "object", "properties": {}}

    def test_schemas_appended_to_existing(self) -> None:
        """MCP tools append to existing LAEE schemas, not replace."""
        existing = [{"type": "function", "function": {"name": "shell_exec", "parameters": {}}}]
        react = _make_react(schemas=existing)

        react.register_mcp_tools("srv", [_mcp_tool_desc("fetch")])

        assert len(react._schemas) == 2
        names = [s["function"]["name"] for s in react._schemas]
        assert names == ["shell_exec", "fetch"]


# ===========================================================================
# TestMCPToolCountProperties — public property accessors
# ===========================================================================


class TestMCPToolCountProperties:
    """Public properties for tool count observability."""

    def test_mcp_client_property(self) -> None:
        """mcp_client property exposes the internal client."""
        client = AsyncMock()
        react = _make_react(mcp_client=client)
        assert react.mcp_client is client

    def test_mcp_client_none(self) -> None:
        """mcp_client returns None when no client configured."""
        react = _make_react()
        assert react.mcp_client is None

    def test_mcp_tool_count_zero(self) -> None:
        """mcp_tool_count is 0 with no MCP tools registered."""
        laee = {"type": "function", "function": {"name": "laee_tool", "parameters": {}}}
        react = _make_react(schemas=[laee])
        assert react.mcp_tool_count == 0

    def test_mcp_tool_count_after_register(self) -> None:
        """mcp_tool_count reflects registered MCP tools."""
        react = _make_react()
        react.register_mcp_tools("srv", [_mcp_tool_desc("a"), _mcp_tool_desc("b")])
        assert react.mcp_tool_count == 2

    def test_laee_tool_count(self) -> None:
        """laee_tool_count = total schemas - MCP tools."""
        existing = [
            {"type": "function", "function": {"name": "shell_exec", "parameters": {}}},
            {"type": "function", "function": {"name": "web_search", "parameters": {}}},
        ]
        react = _make_react(schemas=existing)
        react.register_mcp_tools("srv", [_mcp_tool_desc("fetch")])

        assert react.laee_tool_count == 2
        assert react.mcp_tool_count == 1


# ===========================================================================
# TestContainerMCPStartup — _connect_mcp_servers() flow
# ===========================================================================


@dataclass
class _FakeSettings:
    """Minimal settings stub for container MCP tests."""

    mcp_enabled: bool = True
    mcp_servers: str = '[{"name":"fetch","command":"uvx","args":["mcp-server-fetch"]}]'
    react_enabled: bool = True


class TestContainerMCPStartup:
    """_connect_mcp_servers() auto-connects and registers tools."""

    @pytest.mark.asyncio
    async def test_successful_connect_and_register(self) -> None:
        """Valid config → connect + list_tools + register_mcp_tools."""
        from interface.api.container import AppContainer

        mcp_client = AsyncMock()
        mcp_client.list_tools = AsyncMock(
            return_value=[{"name": "fetch", "description": "Fetch URL"}],
        )

        react = _make_react(mcp_client=mcp_client)

        container = MagicMock(spec=AppContainer)
        container.react_executor = react
        container.settings = _FakeSettings()

        # Call the real method on our mock container
        await AppContainer._connect_mcp_servers(container)

        mcp_client.connect.assert_called_once_with(
            server_name="fetch", command="uvx", args=["mcp-server-fetch"]
        )
        mcp_client.list_tools.assert_called_once_with(server_name="fetch")
        assert "fetch" in react._mcp_tool_names

    @pytest.mark.asyncio
    async def test_empty_servers_config_noop(self) -> None:
        """Empty MCP_SERVERS list → no connections attempted."""
        from interface.api.container import AppContainer

        mcp_client = AsyncMock()
        react = _make_react(mcp_client=mcp_client)

        container = MagicMock(spec=AppContainer)
        container.react_executor = react
        container.settings = _FakeSettings(mcp_servers="[]")

        await AppContainer._connect_mcp_servers(container)

        mcp_client.connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_mcp_disabled_noop(self) -> None:
        """mcp_enabled=False → skip entirely."""
        from interface.api.container import AppContainer

        react = _make_react(mcp_client=AsyncMock())

        container = MagicMock(spec=AppContainer)
        container.react_executor = react
        container.settings = _FakeSettings(mcp_enabled=False)

        await AppContainer._connect_mcp_servers(container)

        react.mcp_client.connect.assert_not_called() if react.mcp_client else None

    @pytest.mark.asyncio
    async def test_no_react_executor_noop(self) -> None:
        """No ReactExecutor → skip entirely."""
        from interface.api.container import AppContainer

        container = MagicMock(spec=AppContainer)
        container.react_executor = None
        container.settings = _FakeSettings()

        # Should not raise
        await AppContainer._connect_mcp_servers(container)

    @pytest.mark.asyncio
    async def test_connect_failure_graceful(self) -> None:
        """Connection failure → log warning, don't crash."""
        from interface.api.container import AppContainer

        mcp_client = AsyncMock()
        mcp_client.connect = AsyncMock(side_effect=ConnectionError("Server not found"))

        react = _make_react(mcp_client=mcp_client)

        container = MagicMock(spec=AppContainer)
        container.react_executor = react
        container.settings = _FakeSettings()

        # Should not raise
        await AppContainer._connect_mcp_servers(container)

        # No tools registered since connect failed
        assert react.mcp_tool_count == 0

    @pytest.mark.asyncio
    async def test_invalid_json_config_noop(self) -> None:
        """Invalid JSON in mcp_servers → no crash."""
        from interface.api.container import AppContainer

        react = _make_react(mcp_client=AsyncMock())

        container = MagicMock(spec=AppContainer)
        container.react_executor = react
        container.settings = _FakeSettings(mcp_servers="not-json")

        await AppContainer._connect_mcp_servers(container)
        assert react.mcp_tool_count == 0

    @pytest.mark.asyncio
    async def test_missing_server_name_skipped(self) -> None:
        """Server config without name → skipped."""
        from interface.api.container import AppContainer

        mcp_client = AsyncMock()
        react = _make_react(mcp_client=mcp_client)

        container = MagicMock(spec=AppContainer)
        container.react_executor = react
        container.settings = _FakeSettings(
            mcp_servers='[{"command":"uvx","args":["mcp-server-fetch"]}]'
        )

        await AppContainer._connect_mcp_servers(container)
        mcp_client.connect.assert_not_called()
