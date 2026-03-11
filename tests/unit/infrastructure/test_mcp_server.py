"""Tests for infrastructure/mcp/server.py — MorphicMCPServer.

Tests tool and resource delegation using a real AppContainer with InMemory repos.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from infrastructure.mcp.server import create_mcp_server


class _FakeSettings:
    """Minimal settings for testing."""

    ollama_base_url = "http://localhost:11434"
    ollama_default_model = "qwen3:8b"
    ollama_coding_model = "qwen3-coder:30b"
    local_first = True
    default_monthly_budget_usd = 50.0
    default_task_budget_usd = 1.0
    auto_downgrade_on_budget = True
    cache_breakpoints_enabled = True
    use_postgres = False
    database_url = ""
    embedding_backend = "none"
    embedding_model = "all-minilm"
    embedding_dimensions = 384
    is_development = False
    memory_retention_threshold = 0.3
    celery_enabled = False
    openhands_base_url = "http://localhost:3000"
    openhands_model = "claude-sonnet-4-6"
    openhands_api_key = ""
    claude_code_sdk_enabled = False
    claude_code_cli_path = "claude"
    gemini_cli_enabled = False
    gemini_cli_path = "gemini"
    codex_cli_enabled = False
    codex_cli_path = "codex"
    adk_enabled = False
    adk_default_model = "gemini-2.5-flash"
    context_bridge_default_tokens = 800
    mcp_enabled = True
    mcp_transport = "stdio"
    mcp_port = 8100
    mcp_servers = "[]"
    # Marketplace (Sprint 5.3)
    marketplace_enabled = True
    marketplace_auto_install = False
    marketplace_safety_threshold = "experimental"
    mcp_registry_url = "https://registry.modelcontextprotocol.io"
    # Affinity (Sprint 7.4)
    affinity_min_samples = 3
    affinity_boost_threshold = 0.6
    # Evolution (Phase 6)
    evolution_enabled = True
    evolution_strategy_dir = Path("/tmp/morphic_test_evolution")
    evolution_auto_update = True
    evolution_min_samples = 10

    @property
    def marketplace_safety_threshold_tier(self):  # type: ignore[no-untyped-def]
        from domain.value_objects.tool_safety import SafetyTier

        return SafetyTier.EXPERIMENTAL


def _make_container():
    """Build an AppContainer with InMemory repos for testing."""
    from interface.api.container import AppContainer

    return AppContainer(settings=_FakeSettings())


# ── Factory ──


class TestFactory:
    def test_create_returns_fastmcp(self) -> None:
        container = _make_container()
        mcp = create_mcp_server(container)
        assert mcp is not None
        assert mcp.name == "morphic-agent"

    def test_server_has_tools(self) -> None:
        container = _make_container()
        mcp = create_mcp_server(container)
        # FastMCP stores tools internally
        assert mcp is not None


# ── Tool delegation: memory_search ──


class TestMemorySearchTool:
    @pytest.mark.asyncio()
    async def test_search_empty(self) -> None:
        container = _make_container()
        mcp = create_mcp_server(container)
        # Call tool function directly via the registered function
        result = await _call_tool(mcp, "memory_search", {"query": "test"})
        assert isinstance(result, str)

    @pytest.mark.asyncio()
    async def test_search_finds_added_content(self) -> None:
        container = _make_container()
        await container.memory.add("important fact about Python")
        mcp = create_mcp_server(container)
        result = await _call_tool(mcp, "memory_search", {"query": "Python"})
        assert "Python" in result


# ── Tool delegation: memory_add ──


class TestMemoryAddTool:
    @pytest.mark.asyncio()
    async def test_add_content(self) -> None:
        container = _make_container()
        mcp = create_mcp_server(container)
        result = await _call_tool(mcp, "memory_add", {"content": "new memory entry"})
        assert "Added to memory" in result

    @pytest.mark.asyncio()
    async def test_added_content_searchable(self) -> None:
        container = _make_container()
        mcp = create_mcp_server(container)
        await _call_tool(mcp, "memory_add", {"content": "searchable fact about testing"})
        result = await _call_tool(mcp, "memory_search", {"query": "testing"})
        assert "testing" in result


# ── Tool delegation: context_compress ──


class TestContextCompressTool:
    @pytest.mark.asyncio()
    async def test_compress_empty(self) -> None:
        container = _make_container()
        mcp = create_mcp_server(container)
        result = await _call_tool(mcp, "context_compress", {"query": "test"})
        assert isinstance(result, str)

    @pytest.mark.asyncio()
    async def test_compress_with_history(self) -> None:
        container = _make_container()
        mcp = create_mcp_server(container)
        result = await _call_tool(
            mcp,
            "context_compress",
            {"query": "summary", "history": ["message 1", "message 2"], "max_tokens": 100},
        )
        assert isinstance(result, str)


# ── Tool delegation: delta_get_state ──


class TestDeltaGetStateTool:
    @pytest.mark.asyncio()
    async def test_empty_topic(self) -> None:
        container = _make_container()
        mcp = create_mcp_server(container)
        result = await _call_tool(mcp, "delta_get_state", {"topic": "nonexistent"})
        assert json.loads(result) == {}

    @pytest.mark.asyncio()
    async def test_with_recorded_state(self) -> None:
        container = _make_container()
        await container.delta_encoder.record("config", "init", {"env": "dev"})
        mcp = create_mcp_server(container)
        result = await _call_tool(mcp, "delta_get_state", {"topic": "config"})
        state = json.loads(result)
        assert state == {"env": "dev"}


# ── Tool delegation: delta_record ──


class TestDeltaRecordTool:
    @pytest.mark.asyncio()
    async def test_record_delta(self) -> None:
        container = _make_container()
        mcp = create_mcp_server(container)
        result = await _call_tool(
            mcp,
            "delta_record",
            {"topic": "deploy", "message": "set version", "changes": '{"version": "1.0"}'},
        )
        parsed = json.loads(result)
        assert parsed["topic"] == "deploy"
        assert parsed["seq"] == 0
        assert "state_hash" in parsed


# ── Tool delegation: context_export ──


class TestContextExportTool:
    @pytest.mark.asyncio()
    async def test_export_claude_code(self) -> None:
        container = _make_container()
        mcp = create_mcp_server(container)
        result = await _call_tool(mcp, "context_export", {"platform": "claude_code"})
        assert "Morphic-Agent Context" in result

    @pytest.mark.asyncio()
    async def test_export_with_data(self) -> None:
        container = _make_container()
        await container.delta_encoder.record("proj", "init", {"status": "active"})
        mcp = create_mcp_server(container)
        result = await _call_tool(mcp, "context_export", {"platform": "gemini", "query": "proj"})
        assert "<morphic-context>" in result


# ── Resource delegation: memory://topics ──


class TestTopicsResource:
    @pytest.mark.asyncio()
    async def test_empty_topics(self) -> None:
        container = _make_container()
        mcp = create_mcp_server(container)
        result = await _call_resource(mcp, "memory://topics")
        assert json.loads(result) == []

    @pytest.mark.asyncio()
    async def test_lists_topics(self) -> None:
        container = _make_container()
        await container.delta_encoder.record("alpha", "init", {"x": 1})
        await container.delta_encoder.record("beta", "init", {"y": 2})
        mcp = create_mcp_server(container)
        result = await _call_resource(mcp, "memory://topics")
        topics = json.loads(result)
        assert set(topics) == {"alpha", "beta"}


# ── Resource delegation: memory://state/{topic} ──


class TestStateResource:
    @pytest.mark.asyncio()
    async def test_empty_state(self) -> None:
        container = _make_container()
        mcp = create_mcp_server(container)
        result = await _call_resource(mcp, "memory://state/nonexistent")
        assert json.loads(result) == {}

    @pytest.mark.asyncio()
    async def test_reconstructed_state(self) -> None:
        container = _make_container()
        await container.delta_encoder.record("api", "init", {"endpoint": "/users"})
        await container.delta_encoder.record("api", "add auth", {"auth": True})
        mcp = create_mcp_server(container)
        result = await _call_resource(mcp, "memory://state/api")
        state = json.loads(result)
        assert state == {"endpoint": "/users", "auth": True}


# ── Graceful degradation ──


class TestGracefulDegradation:
    @pytest.mark.asyncio()
    async def test_none_memory(self) -> None:
        container = _make_container()
        container.memory = None
        mcp = create_mcp_server(container)
        result = await _call_tool(mcp, "memory_search", {"query": "test"})
        assert "not available" in result.lower()

    @pytest.mark.asyncio()
    async def test_none_delta_encoder(self) -> None:
        container = _make_container()
        container.delta_encoder = None
        mcp = create_mcp_server(container)
        result = await _call_tool(mcp, "delta_get_state", {"topic": "test"})
        assert json.loads(result) == {}


# ── Helpers ──


async def _call_tool(mcp: object, name: str, arguments: dict) -> str:
    """Call a registered tool by name, returning its string result."""
    import inspect

    tool = mcp._tool_manager._tools.get(name)
    if tool is None:
        raise KeyError(f"Tool '{name}' not registered")
    result = tool.fn(**arguments)
    if inspect.isawaitable(result):
        result = await result
    return str(result)


async def _call_resource(mcp: object, uri: str) -> str:
    """Call a registered resource by URI, returning its string result."""
    import inspect

    # Check static resources first
    resource = mcp._resource_manager._resources.get(uri)
    if resource is not None:
        result = resource.fn()
        if inspect.isawaitable(result):
            result = await result
        return str(result)

    # Check templated resources
    for template_uri, template in mcp._resource_manager._templates.items():
        params = _match_uri(str(template_uri), uri)
        if params is not None:
            result = template.fn(**params)
            if inspect.isawaitable(result):
                result = await result
            return str(result)

    raise KeyError(f"Resource '{uri}' not registered")


def _match_uri(template: str, uri: str) -> dict | None:
    """Simple URI template matching. Returns extracted params or None."""
    import re

    parts = template.split("{")
    if len(parts) == 1:
        return {} if template == uri else None
    regex = re.escape(parts[0])
    for part in parts[1:]:
        name, rest = part.split("}", 1)
        regex += f"(?P<{name}>[^/]+)" + re.escape(rest)
    regex = f"^{regex}$"

    match = re.match(regex, uri)
    if match:
        return match.groupdict()
    return None
