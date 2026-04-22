"""Tests for Fallback strategy inspection CLI — Sprint 25.2 (TD-133).

Uses _set_container() to inject a mock container, verifying that CLI
commands correctly call execution_record_repo methods and format output.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from typer.testing import CliRunner

from domain.entities.execution_record import ExecutionRecord
from domain.ports.execution_record_repository import ExecutionStats
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    task_id: str = "task-1",
    goal: str = "test fallback routing",
    engine: AgentEngineType = AgentEngineType.OLLAMA,
    model: str = "qwen3:8b",
    success: bool = True,
    error: str | None = None,
    cost: float = 0.0,
    duration: float = 1.5,
) -> ExecutionRecord:
    return ExecutionRecord(
        task_id=task_id,
        task_type=TaskType.SIMPLE_QA,
        goal=goal,
        engine_used=engine,
        model_used=model,
        success=success,
        error_message=error,
        cost_usd=cost,
        duration_seconds=duration,
        created_at=datetime(2026, 3, 29, 14, 0, 0),
    )


def _make_stats(
    total: int = 10,
    success: int = 8,
    failure: int = 2,
    avg_cost: float = 0.01,
    avg_duration: float = 2.0,
    engines: dict | None = None,
    models: dict | None = None,
) -> ExecutionStats:
    return ExecutionStats(
        total_count=total,
        success_count=success,
        failure_count=failure,
        avg_cost_usd=avg_cost,
        avg_duration_seconds=avg_duration,
        engine_distribution=engines or {"ollama": 7, "claude_code": 3},
        model_distribution=models or {"qwen3:8b": 7, "claude-sonnet-4-6": 3},
    )


def _make_container(
    records: list[ExecutionRecord] | None = None,
    stats: ExecutionStats | None = None,
):
    """Build a mock container with execution_record_repo."""
    records = records or []
    stats = stats or _make_stats()
    repo = MagicMock()
    repo.list_recent = AsyncMock(return_value=records)
    repo.list_by_task_type = AsyncMock(return_value=records)
    repo.list_failures = AsyncMock(return_value=records)
    repo.get_stats = AsyncMock(return_value=stats)
    return MagicMock(execution_record_repo=repo)


def _invoke(*args: str, container=None):
    from interface.cli._utils import _set_container
    from interface.cli.main import app

    if container:
        _set_container(container)
    result = runner.invoke(app, list(args))
    _set_container(None)
    return result


# ---------------------------------------------------------------------------
# morphic fallback history
# ---------------------------------------------------------------------------


class TestHistoryCommand:
    def test_history_empty(self):
        c = _make_container([])
        result = _invoke("fallback", "history", container=c)
        assert result.exit_code == 0
        assert "No execution records found" in result.output

    def test_history_with_records(self):
        records = [
            _make_record(),
            _make_record(
                task_id="task-2",
                engine=AgentEngineType.CLAUDE_CODE,
                model="claude-sonnet-4-6",
                success=False,
                error="API timeout",
                cost=0.003,
            ),
        ]
        c = _make_container(records)
        result = _invoke("fallback", "history", container=c)
        assert result.exit_code == 0
        assert "Execution History" in result.output
        c.execution_record_repo.list_recent.assert_called_once_with(limit=50)

    def test_history_filtered_by_type(self):
        records = [_make_record()]
        c = _make_container(records)
        result = _invoke(
            "fallback", "history", "--type", "code_generation", container=c
        )
        assert result.exit_code == 0
        c.execution_record_repo.list_by_task_type.assert_called_once_with(
            TaskType.CODE_GENERATION, limit=50
        )

    def test_history_invalid_type(self):
        c = _make_container([])
        result = _invoke("fallback", "history", "--type", "invalid", container=c)
        assert result.exit_code == 1
        assert "Unknown task type" in result.output

    def test_history_with_limit(self):
        records = [_make_record()]
        c = _make_container(records)
        result = _invoke("fallback", "history", "--limit", "10", container=c)
        assert result.exit_code == 0
        c.execution_record_repo.list_recent.assert_called_once_with(limit=10)


# ---------------------------------------------------------------------------
# morphic fallback failures
# ---------------------------------------------------------------------------


class TestFailuresCommand:
    def test_failures_empty(self):
        c = _make_container([])
        result = _invoke("fallback", "failures", container=c)
        assert result.exit_code == 0
        assert "No failed executions found" in result.output

    def test_failures_with_records(self):
        records = [
            _make_record(success=False, error="timeout"),
            _make_record(
                task_id="task-2",
                success=False,
                error="model not available",
            ),
        ]
        c = _make_container(records)
        result = _invoke("fallback", "failures", container=c)
        assert result.exit_code == 0
        assert "Failed Executions" in result.output

    def test_failures_with_since(self):
        records = [_make_record(success=False, error="err")]
        c = _make_container(records)
        result = _invoke(
            "fallback", "failures", "--since", "2026-03-28", container=c
        )
        assert result.exit_code == 0
        call_args = c.execution_record_repo.list_failures.call_args
        assert call_args.kwargs["since"] is not None

    def test_failures_invalid_date(self):
        c = _make_container([])
        result = _invoke(
            "fallback", "failures", "--since", "not-a-date", container=c
        )
        assert result.exit_code == 1
        assert "Invalid date format" in result.output


# ---------------------------------------------------------------------------
# morphic fallback stats
# ---------------------------------------------------------------------------


class TestStatsCommand:
    def test_stats_default(self):
        c = _make_container()
        result = _invoke("fallback", "stats", container=c)
        assert result.exit_code == 0
        assert "Execution Statistics" in result.output
        c.execution_record_repo.get_stats.assert_called_once_with(
            task_type=None
        )

    def test_stats_with_type(self):
        c = _make_container()
        result = _invoke(
            "fallback", "stats", "--type", "simple_qa", container=c
        )
        assert result.exit_code == 0
        c.execution_record_repo.get_stats.assert_called_once_with(
            task_type=TaskType.SIMPLE_QA
        )

    def test_stats_invalid_type(self):
        c = _make_container()
        result = _invoke("fallback", "stats", "--type", "invalid", container=c)
        assert result.exit_code == 1
        assert "Unknown task type" in result.output

    def test_stats_shows_distributions(self):
        stats = _make_stats(
            engines={"ollama": 5, "gemini_cli": 3},
            models={"qwen3:8b": 5, "gemini-2.5-flash": 3},
        )
        c = _make_container(stats=stats)
        result = _invoke("fallback", "stats", container=c)
        assert result.exit_code == 0
        assert "Execution Statistics" in result.output


# ---------------------------------------------------------------------------
# Formatter tests
# ---------------------------------------------------------------------------


class TestExecutionFormatters:
    def test_print_execution_history_table(self):
        from interface.cli.formatters import print_execution_history_table

        records = [
            _make_record(),
            _make_record(
                success=False, error="API error", cost=0.05
            ),
        ]
        print_execution_history_table(records)

    def test_print_execution_history_table_empty(self):
        from interface.cli.formatters import print_execution_history_table

        print_execution_history_table([])

    def test_print_execution_stats(self):
        from interface.cli.formatters import print_execution_stats

        stats = _make_stats()
        print_execution_stats(stats)

    def test_print_execution_stats_empty_distributions(self):
        from interface.cli.formatters import print_execution_stats

        stats = _make_stats(engines={}, models={})
        print_execution_stats(stats)
