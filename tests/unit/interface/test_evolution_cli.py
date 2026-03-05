"""Tests for evolution CLI commands."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from application.use_cases.analyze_execution import AnalyzeExecutionUseCase
from application.use_cases.systemic_evolution import SystemicEvolutionUseCase
from application.use_cases.update_strategy import UpdateStrategyUseCase
from domain.entities.execution_record import ExecutionRecord
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType
from infrastructure.evolution.strategy_store import StrategyStore
from infrastructure.persistence.in_memory_execution_record import (
    InMemoryExecutionRecordRepository,
)
from interface.cli.main import app


def _rec(success: bool = True, error: str | None = None) -> ExecutionRecord:
    return ExecutionRecord(
        task_id="t1",
        task_type=TaskType.SIMPLE_QA,
        engine_used=AgentEngineType.OLLAMA,
        model_used="ollama/qwen3:8b",
        success=success,
        error_message=error,
        cost_usd=0.01,
        duration_seconds=1.0,
    )


def _make_container():  # type: ignore[no-untyped-def]
    repo = InMemoryExecutionRecordRepository()
    store = StrategyStore(base_dir=Path(tempfile.mkdtemp()))
    analyze = AnalyzeExecutionUseCase(repo=repo)
    update = UpdateStrategyUseCase(
        execution_repo=repo,
        strategy_store=store,
        min_samples=2,
    )
    systemic = SystemicEvolutionUseCase(
        analyze_execution=analyze,
        update_strategy=update,
        discover_tools=None,
    )
    container = MagicMock()
    container.analyze_execution = analyze
    container.update_strategy = update
    container.systemic_evolution = systemic
    container._repo = repo  # for test data injection
    return container


def _seed(repo: InMemoryExecutionRecordRepository, records: list[ExecutionRecord]) -> None:
    """Synchronously seed records into the repo (bypass async)."""
    repo._records.extend(records)


runner = CliRunner()


class TestEvolutionCLI:
    def setup_method(self) -> None:
        self.container = _make_container()

    def _invoke(self, args: list[str]) -> object:
        with patch("interface.cli.main._get_container", return_value=self.container):
            return runner.invoke(app, args)

    def test_stats_empty(self) -> None:
        result = self._invoke(["evolution", "stats"])
        assert result.exit_code == 0
        assert "Total executions" in result.output

    def test_stats_with_data(self) -> None:
        _seed(self.container._repo, [_rec(success=True), _rec(success=False, error="err")])
        result = self._invoke(["evolution", "stats"])
        assert result.exit_code == 0

    def test_failures_empty(self) -> None:
        result = self._invoke(["evolution", "failures"])
        assert result.exit_code == 0
        assert "No failure patterns found" in result.output

    def test_failures_with_data(self) -> None:
        _seed(
            self.container._repo,
            [
                _rec(success=False, error="timeout"),
                _rec(success=False, error="timeout"),
            ],
        )
        result = self._invoke(["evolution", "failures"])
        assert result.exit_code == 0

    def test_update(self) -> None:
        result = self._invoke(["evolution", "update"])
        assert result.exit_code == 0
        assert "Strategy update complete" in result.output

    def test_report(self) -> None:
        result = self._invoke(["evolution", "report"])
        assert result.exit_code == 0
        assert "Evolution Report" in result.output

    def test_stats_invalid_task_type(self) -> None:
        result = self._invoke(["evolution", "stats", "--type", "invalid"])
        assert result.exit_code == 1

    def test_report_with_data(self) -> None:
        _seed(self.container._repo, [_rec(success=True) for _ in range(5)])
        result = self._invoke(["evolution", "report"])
        assert result.exit_code == 0
        assert "systemic" in result.output

    def test_update_with_data(self) -> None:
        _seed(self.container._repo, [_rec(success=True) for _ in range(3)])
        result = self._invoke(["evolution", "update"])
        assert result.exit_code == 0
        assert "Model preferences updated" in result.output
