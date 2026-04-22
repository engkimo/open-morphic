"""Tests for benchmark CLI commands — Sprint 7.6."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.cognitive.adapters import (
    ADKContextAdapter,
    ClaudeCodeContextAdapter,
    CodexContextAdapter,
    GeminiContextAdapter,
    OllamaContextAdapter,
    OpenHandsContextAdapter,
)
from interface.cli.main import app

runner = CliRunner()


def _make_mock_container() -> MagicMock:
    container = MagicMock()
    container._context_adapters = {
        AgentEngineType.CLAUDE_CODE: ClaudeCodeContextAdapter(),
        AgentEngineType.GEMINI_CLI: GeminiContextAdapter(),
        AgentEngineType.CODEX_CLI: CodexContextAdapter(),
        AgentEngineType.OPENHANDS: OpenHandsContextAdapter(),
        AgentEngineType.ADK: ADKContextAdapter(),
        AgentEngineType.OLLAMA: OllamaContextAdapter(),
    }
    return container


@pytest.fixture(autouse=True)
def _mock_container(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "interface.cli.commands.benchmark._get_container",
        _make_mock_container,
    )


class TestBenchmarkCLI:
    """Benchmark CLI command tests."""

    def test_benchmark_run(self) -> None:
        result = runner.invoke(app, ["benchmark", "run"])
        assert result.exit_code == 0
        assert "Context Continuity" in result.output or "Overall Score" in result.output

    def test_benchmark_continuity(self) -> None:
        result = runner.invoke(app, ["benchmark", "continuity"])
        assert result.exit_code == 0
        assert "Context Continuity" in result.output

    def test_benchmark_dedup(self) -> None:
        result = runner.invoke(app, ["benchmark", "dedup"])
        assert result.exit_code == 0
        assert "Dedup Accuracy" in result.output

    def test_benchmark_help(self) -> None:
        result = runner.invoke(app, ["benchmark", "--help"])
        assert result.exit_code == 0
        assert "continuity" in result.output
        assert "dedup" in result.output
        assert "run" in result.output
