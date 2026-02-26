"""Tests for infrastructure/memory/context_bridge.py — ContextBridge.

Async tests using InMemoryMemoryRepository.
"""

from __future__ import annotations

import pytest

from infrastructure.memory.context_bridge import (
    SUPPORTED_PLATFORMS,
    ContextBridge,
    ExportResult,
)
from infrastructure.memory.delta_encoder import DeltaEncoderManager
from infrastructure.memory.memory_hierarchy import MemoryHierarchy
from infrastructure.persistence.in_memory import InMemoryMemoryRepository

# ── ExportResult ──


class TestExportResult:
    def test_frozen(self) -> None:
        r = ExportResult(platform="claude_code", content="test", token_estimate=1)
        with pytest.raises(AttributeError):
            r.platform = "other"  # type: ignore[misc]

    def test_fields(self) -> None:
        r = ExportResult(platform="chatgpt", content="hello world", token_estimate=3)
        assert r.platform == "chatgpt"
        assert r.content == "hello world"
        assert r.token_estimate == 3


# ── export — unsupported platform ──


class TestExportValidation:
    @pytest.mark.asyncio()
    async def test_unsupported_platform_raises(self) -> None:
        bridge = ContextBridge()
        with pytest.raises(ValueError, match="Unsupported platform"):
            await bridge.export("invalid_platform")

    @pytest.mark.asyncio()
    async def test_supported_platforms(self) -> None:
        assert "claude_code" in SUPPORTED_PLATFORMS
        assert "chatgpt" in SUPPORTED_PLATFORMS
        assert "cursor" in SUPPORTED_PLATFORMS
        assert "gemini" in SUPPORTED_PLATFORMS


# ── export — empty / no ports ──


class TestExportEmpty:
    @pytest.mark.asyncio()
    async def test_empty_no_ports(self) -> None:
        bridge = ContextBridge()
        result = await bridge.export("claude_code")
        assert result.platform == "claude_code"
        assert result.token_estimate >= 1
        assert isinstance(result.content, str)

    @pytest.mark.asyncio()
    async def test_empty_no_query(self) -> None:
        repo = InMemoryMemoryRepository()
        memory = MemoryHierarchy(memory_repo=repo)
        bridge = ContextBridge(memory=memory)
        result = await bridge.export("chatgpt", query="")
        assert result.platform == "chatgpt"
        assert isinstance(result.content, str)


# ── export — claude_code format ──


class TestClaudeCodeFormat:
    @pytest.mark.asyncio()
    async def test_contains_header(self) -> None:
        bridge = ContextBridge()
        result = await bridge.export("claude_code", query="test query")
        assert "# Morphic-Agent Context" in result.content

    @pytest.mark.asyncio()
    async def test_includes_query(self) -> None:
        bridge = ContextBridge()
        result = await bridge.export("claude_code", query="search term")
        assert "search term" in result.content

    @pytest.mark.asyncio()
    async def test_includes_state(self) -> None:
        repo = InMemoryMemoryRepository()
        delta = DeltaEncoderManager(memory_repo=repo)
        await delta.record("project", "init", {"name": "Morphic", "version": "0.4"})
        bridge = ContextBridge(delta_encoder=delta)
        result = await bridge.export("claude_code")
        assert "project" in result.content
        assert "Morphic" in result.content

    @pytest.mark.asyncio()
    async def test_includes_memory(self) -> None:
        repo = InMemoryMemoryRepository()
        memory = MemoryHierarchy(memory_repo=repo)
        await memory.add("important fact about testing")
        bridge = ContextBridge(memory=memory)
        result = await bridge.export("claude_code", query="testing")
        assert "important fact about testing" in result.content


# ── export — chatgpt format ──


class TestChatGPTFormat:
    @pytest.mark.asyncio()
    async def test_contains_sections(self) -> None:
        bridge = ContextBridge()
        result = await bridge.export("chatgpt", query="test")
        assert "What would you like ChatGPT to know?" in result.content
        assert "How should ChatGPT respond?" in result.content

    @pytest.mark.asyncio()
    async def test_includes_state(self) -> None:
        repo = InMemoryMemoryRepository()
        delta = DeltaEncoderManager(memory_repo=repo)
        await delta.record("deploy", "init", {"env": "production"})
        bridge = ContextBridge(delta_encoder=delta)
        result = await bridge.export("chatgpt")
        assert "deploy" in result.content
        assert "production" in result.content


# ── export — cursor format ──


class TestCursorFormat:
    @pytest.mark.asyncio()
    async def test_numbered_rules(self) -> None:
        repo = InMemoryMemoryRepository()
        delta = DeltaEncoderManager(memory_repo=repo)
        await delta.record("config", "init", {"mode": "dev"})
        bridge = ContextBridge(delta_encoder=delta)
        result = await bridge.export("cursor")
        assert "1." in result.content
        assert "config" in result.content

    @pytest.mark.asyncio()
    async def test_includes_focus(self) -> None:
        bridge = ContextBridge()
        result = await bridge.export("cursor", query="authentication")
        assert "authentication" in result.content


# ── export — gemini format ──


class TestGeminiFormat:
    @pytest.mark.asyncio()
    async def test_xml_structure(self) -> None:
        bridge = ContextBridge()
        result = await bridge.export("gemini")
        assert "<morphic-context>" in result.content
        assert "</morphic-context>" in result.content

    @pytest.mark.asyncio()
    async def test_includes_state_tags(self) -> None:
        repo = InMemoryMemoryRepository()
        delta = DeltaEncoderManager(memory_repo=repo)
        await delta.record("api", "init", {"version": "v2"})
        bridge = ContextBridge(delta_encoder=delta)
        result = await bridge.export("gemini")
        assert "<state>" in result.content
        assert "</state>" in result.content
        assert "v2" in result.content

    @pytest.mark.asyncio()
    async def test_includes_focus(self) -> None:
        bridge = ContextBridge()
        result = await bridge.export("gemini", query="deployment")
        assert "<focus>deployment</focus>" in result.content


# ── export_all ──


class TestExportAll:
    @pytest.mark.asyncio()
    async def test_returns_all_platforms(self) -> None:
        bridge = ContextBridge()
        results = await bridge.export_all()
        assert len(results) == len(SUPPORTED_PLATFORMS)
        platforms = {r.platform for r in results}
        assert platforms == set(SUPPORTED_PLATFORMS)

    @pytest.mark.asyncio()
    async def test_all_have_content(self) -> None:
        repo = InMemoryMemoryRepository()
        delta = DeltaEncoderManager(memory_repo=repo)
        await delta.record("test", "init", {"key": "value"})
        bridge = ContextBridge(delta_encoder=delta)
        results = await bridge.export_all()
        for result in results:
            assert len(result.content) > 0
            assert result.token_estimate >= 1


# ── token budget ──


class TestTokenBudget:
    @pytest.mark.asyncio()
    async def test_default_budget(self) -> None:
        bridge = ContextBridge(default_max_tokens=100)
        result = await bridge.export("claude_code")
        assert result.token_estimate >= 1

    @pytest.mark.asyncio()
    async def test_custom_budget(self) -> None:
        bridge = ContextBridge(default_max_tokens=100)
        result = await bridge.export("claude_code", max_tokens=50)
        # Should not crash with a small budget
        assert result.token_estimate >= 1


# ── graceful degradation ──


class TestGracefulDegradation:
    @pytest.mark.asyncio()
    async def test_no_memory(self) -> None:
        bridge = ContextBridge(memory=None)
        result = await bridge.export("claude_code", query="test")
        assert isinstance(result.content, str)

    @pytest.mark.asyncio()
    async def test_no_context_zipper(self) -> None:
        bridge = ContextBridge(context_zipper=None)
        result = await bridge.export("chatgpt", query="test")
        assert isinstance(result.content, str)

    @pytest.mark.asyncio()
    async def test_no_delta_encoder(self) -> None:
        bridge = ContextBridge(delta_encoder=None)
        result = await bridge.export("cursor", query="test")
        assert isinstance(result.content, str)

    @pytest.mark.asyncio()
    async def test_all_ports_none(self) -> None:
        bridge = ContextBridge()
        for platform in SUPPORTED_PLATFORMS:
            result = await bridge.export(platform, query="anything")
            assert isinstance(result.content, str)
            assert result.token_estimate >= 1
