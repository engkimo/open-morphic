"""Tests for AgentEngine port — dataclasses and ABC.

Sprint 4.1: AgentEngine Domain Foundation
"""

from __future__ import annotations

import time
from abc import ABC
from datetime import UTC, datetime

import pytest

from domain.ports.agent_engine import (
    AgentEngineCapabilities,
    AgentEnginePort,
    AgentEngineResult,
)
from domain.value_objects.agent_engine import AgentEngineType

# ---------------------------------------------------------------------------
# TestAgentEngineResult
# ---------------------------------------------------------------------------


class TestAgentEngineResult:
    """AgentEngineResult dataclass construction and defaults."""

    def test_minimal_construction(self) -> None:
        """Minimal fields: engine + success + output."""
        result = AgentEngineResult(
            engine=AgentEngineType.CLAUDE_CODE,
            success=True,
            output="done",
        )
        assert result.engine == AgentEngineType.CLAUDE_CODE
        assert result.success is True
        assert result.output == "done"
        assert result.artifacts == []
        assert result.cost_usd == 0.0
        assert result.duration_seconds == 0.0
        assert result.model_used is None
        assert result.error is None
        assert result.metadata == {}

    def test_full_construction(self) -> None:
        """All fields specified explicitly."""
        ts = datetime(2026, 2, 27, tzinfo=UTC)
        result = AgentEngineResult(
            engine=AgentEngineType.OPENHANDS,
            success=False,
            output="timeout",
            artifacts=["file.py", "test.py"],
            cost_usd=0.42,
            duration_seconds=123.4,
            model_used="claude-sonnet-4-6",
            error="timeout after 120s",
            metadata={"session_id": "abc"},
            timestamp=ts,
        )
        assert result.engine == AgentEngineType.OPENHANDS
        assert result.success is False
        assert result.artifacts == ["file.py", "test.py"]
        assert result.cost_usd == 0.42
        assert result.duration_seconds == 123.4
        assert result.model_used == "claude-sonnet-4-6"
        assert result.error == "timeout after 120s"
        assert result.metadata == {"session_id": "abc"}
        assert result.timestamp == ts

    def test_defaults(self) -> None:
        """Default values are sensible."""
        result = AgentEngineResult(
            engine=AgentEngineType.OLLAMA,
            success=True,
            output="ok",
        )
        assert result.cost_usd == 0.0
        assert result.artifacts == []
        assert result.metadata == {}

    def test_timestamp_auto(self) -> None:
        """Timestamp defaults to approximately now."""
        before = datetime.now(tz=UTC)
        time.sleep(0.01)
        result = AgentEngineResult(
            engine=AgentEngineType.OLLAMA,
            success=True,
            output="ok",
        )
        time.sleep(0.01)
        after = datetime.now(tz=UTC)
        assert before <= result.timestamp <= after


# ---------------------------------------------------------------------------
# TestAgentEngineCapabilities
# ---------------------------------------------------------------------------


class TestAgentEngineCapabilities:
    """AgentEngineCapabilities dataclass."""

    def test_defaults(self) -> None:
        cap = AgentEngineCapabilities(engine_type=AgentEngineType.OLLAMA)
        assert cap.engine_type == AgentEngineType.OLLAMA
        assert cap.max_context_tokens == 0
        assert cap.supports_sandbox is False
        assert cap.supports_parallel is False
        assert cap.supports_mcp is False
        assert cap.supports_streaming is False
        assert cap.cost_per_hour_usd == 0.0

    def test_custom_values(self) -> None:
        cap = AgentEngineCapabilities(
            engine_type=AgentEngineType.OPENHANDS,
            max_context_tokens=200_000,
            supports_sandbox=True,
            supports_parallel=True,
            supports_mcp=False,
            supports_streaming=True,
            cost_per_hour_usd=3.50,
        )
        assert cap.max_context_tokens == 200_000
        assert cap.supports_sandbox is True
        assert cap.supports_parallel is True
        assert cap.supports_mcp is False
        assert cap.supports_streaming is True
        assert cap.cost_per_hour_usd == 3.50

    def test_frozen(self) -> None:
        """Capabilities are frozen (immutable)."""
        cap = AgentEngineCapabilities(engine_type=AgentEngineType.GEMINI_CLI)
        with pytest.raises(AttributeError):
            cap.max_context_tokens = 999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestAgentEnginePortIsAbstract
# ---------------------------------------------------------------------------


class TestAgentEnginePortIsAbstract:
    """AgentEnginePort cannot be instantiated directly."""

    def test_cannot_instantiate(self) -> None:
        assert issubclass(AgentEnginePort, ABC)
        with pytest.raises(TypeError):
            AgentEnginePort()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# Backward compatibility: extended TaskType
# ---------------------------------------------------------------------------


class TestExtendedTaskTypeBackwardCompat:
    """Adding 2 new TaskType members doesn't break existing usage."""

    def test_original_six_unchanged(self) -> None:
        from domain.value_objects.model_tier import TaskType

        original = [
            "simple_qa",
            "code_generation",
            "complex_reasoning",
            "file_operation",
            "long_context",
            "multimodal",
        ]
        for val in original:
            assert TaskType(val).value == val

    def test_task_model_map_fallthrough(self) -> None:
        """New task types fall through dict.get() to default — no KeyError."""
        from domain.value_objects.model_tier import TaskType

        # Simulate the pattern used in LiteLLMGateway
        task_model_map: dict[str, list[str]] = {
            "simple_qa": ["ollama/qwen3:8b"],
            "code_generation": ["ollama/qwen3-coder:30b"],
        }
        # New types fall through to default
        result = task_model_map.get(TaskType.LONG_RUNNING_DEV.value, ["default_model"])
        assert result == ["default_model"]
        result2 = task_model_map.get(TaskType.WORKFLOW_PIPELINE.value, ["default_model"])
        assert result2 == ["default_model"]
