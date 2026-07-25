"""Tests for benchmark CLI commands — Sprint 7.6."""

from __future__ import annotations

import json
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
        assert "agent-cli" in result.output
        assert "continuity" in result.output
        assert "dedup" in result.output
        assert "run" in result.output

    def test_agent_cli_evaluates_recorded_results_as_json(self, tmp_path: object) -> None:
        from pathlib import Path

        root = Path(str(tmp_path))
        manifest = root / "manifest.json"
        results = root / "results.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "benchmark_id": "cli-001",
                    "task": {
                        "id": "task-001",
                        "goal": "Apply one identical change",
                        "workspace_revision": "abc123",
                        "checks": ["unit"],
                        "handoff_assertions": ["decision"],
                    },
                    "arms": ["codex_cli", "claude_code", "morphic_control"],
                    "repetitions": 1,
                }
            ),
            encoding="utf-8",
        )
        results.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "benchmark_id": "cli-001",
                    "task_id": "task-001",
                    "observations": [
                        {
                            "arm": arm,
                            "trial": 1,
                            "completed": True,
                            "accepted_patch": True,
                            "passed_checks": ["unit"],
                            "elapsed_seconds": 10.0,
                            "cost_usd": 0.1,
                            "human_interventions": 0,
                            "recovery_attempted": False,
                            "recovery_succeeded": False,
                            "passed_handoff_assertions": ["decision"],
                        }
                        for arm in ("codex_cli", "claude_code", "morphic_control")
                    ],
                }
            ),
            encoding="utf-8",
        )

        result = runner.invoke(
            app,
            [
                "benchmark",
                "agent-cli",
                "--manifest",
                str(manifest),
                "--results",
                str(results),
                "--json",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["benchmark_id"] == "cli-001"
        assert payload["observation_count"] == 3
        assert "overall_score" not in payload

        human_result = runner.invoke(
            app,
            [
                "benchmark",
                "agent-cli",
                "--manifest",
                str(manifest),
                "--results",
                str(results),
            ],
        )
        assert human_result.exit_code == 0
        assert "Metric leaders" in human_result.output
        assert "completion_rate" in human_result.output

    def test_agent_cli_reports_invalid_recorded_results(self, tmp_path: object) -> None:
        from pathlib import Path

        root = Path(str(tmp_path))
        manifest = root / "manifest.json"
        results = root / "results.json"
        manifest.write_text("{}", encoding="utf-8")
        results.write_text("{}", encoding="utf-8")

        result = runner.invoke(
            app,
            [
                "benchmark",
                "agent-cli",
                "--manifest",
                str(manifest),
                "--results",
                str(results),
            ],
        )

        assert result.exit_code == 1
        assert "Invalid agent CLI benchmark input" in result.output
