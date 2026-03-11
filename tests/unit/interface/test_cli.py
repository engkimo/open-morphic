"""Tests for the Morphic CLI — Sprints 2.9, 2.10, 2.11.

Uses typer.testing.CliRunner + monkeypatched container (same pattern as test_api.py).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from typer.testing import CliRunner

from application.use_cases.cost_estimator import CostEstimator
from application.use_cases.interactive_plan import InteractivePlanUseCase
from domain.entities.cost import CostRecord
from domain.entities.task import SubTask, TaskEntity
from domain.value_objects.status import SubTaskStatus, TaskStatus
from infrastructure.llm.cost_tracker import CostTracker
from infrastructure.memory.memory_hierarchy import MemoryHierarchy
from infrastructure.persistence.in_memory import (
    InMemoryCostRepository,
    InMemoryMemoryRepository,
    InMemoryPlanRepository,
    InMemoryTaskRepository,
)
from interface.cli import main as cli_main
from interface.cli.main import app

runner = CliRunner()


# ── Mock container (same pattern as test_api.py) ──


class _MockContainer:
    """Lightweight DI container with mock LLM for CLI testing."""

    def __init__(self) -> None:
        self.settings = _FakeSettings()
        self.task_repo = InMemoryTaskRepository()
        self.cost_repo = InMemoryCostRepository()
        self.memory_repo = InMemoryMemoryRepository()
        self.plan_repo = InMemoryPlanRepository()
        self.memory = MemoryHierarchy(memory_repo=self.memory_repo)

        # Mock LLM-dependent services
        self.ollama = AsyncMock()
        self.ollama.is_running = AsyncMock(return_value=True)
        self.ollama.list_models = AsyncMock(return_value=["qwen3:8b", "qwen3-coder:30b"])
        self.ollama.pull_model = AsyncMock(return_value=True)

        self.llm = AsyncMock()
        self.llm.list_models = AsyncMock(return_value=["qwen3:8b", "qwen3-coder:30b"])

        self.cost_tracker = CostTracker(self.cost_repo)

        self.create_task = AsyncMock()
        self.execute_task = AsyncMock()

        # Planning
        self.task_engine = AsyncMock()
        from domain.entities.task import SubTask

        self.task_engine.decompose = AsyncMock(
            return_value=[SubTask(description="step 1"), SubTask(description="step 2")]
        )
        self.cost_estimator = CostEstimator()
        self.interactive_plan = InteractivePlanUseCase(
            engine=self.task_engine,
            cost_estimator=self.cost_estimator,
            plan_repo=self.plan_repo,
            task_repo=self.task_repo,
        )


class _FakeSettings:
    ollama_default_model: str = "qwen3:8b"
    default_monthly_budget_usd: float = 50.0
    affinity_min_samples: int = 3
    affinity_boost_threshold: float = 0.6


def _make_task(
    goal: str = "test goal",
    status: TaskStatus = TaskStatus.PENDING,
    subtasks: list[SubTask] | None = None,
) -> TaskEntity:
    return TaskEntity(goal=goal, status=status, subtasks=subtasks or [])


@pytest.fixture(autouse=True)
def _inject_container(monkeypatch: pytest.MonkeyPatch) -> _MockContainer:
    """Inject mock container into CLI for every test."""
    container = _MockContainer()
    monkeypatch.setattr(cli_main, "_container_instance", container)
    return container


@pytest.fixture()
def container(_inject_container: _MockContainer) -> _MockContainer:
    return _inject_container


# ═══════════════════════════════════════════════════════════════
# Sprint 2.9: CLI Foundation
# ═══════════════════════════════════════════════════════════════


class TestMainApp:
    def test_version(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "morphic-agent" in result.output

    def test_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "task" in result.output
        assert "model" in result.output
        assert "cost" in result.output

    def test_no_args_shows_help(self) -> None:
        result = runner.invoke(app, [])
        # typer/click returns exit code 0 or 2 for no_args_is_help
        assert result.exit_code in (0, 2)
        assert "Usage" in result.output


# ═══════════════════════════════════════════════════════════════
# Sprint 2.10: Task Commands
# ═══════════════════════════════════════════════════════════════


class TestTaskCommands:
    def test_create_success(self, container: _MockContainer) -> None:
        task = _make_task(
            "fibonacci",
            status=TaskStatus.SUCCESS,
            subtasks=[SubTask(description="code it", status=SubTaskStatus.SUCCESS)],
        )
        container.create_task.execute = AsyncMock(return_value=task)
        container.execute_task.execute = AsyncMock(return_value=task)

        result = runner.invoke(app, ["task", "create", "fibonacci"])
        assert result.exit_code == 0
        assert "fibonacci" in result.output

    def test_create_no_wait(self, container: _MockContainer) -> None:
        task = _make_task("quick task")
        container.create_task.execute = AsyncMock(return_value=task)

        result = runner.invoke(app, ["task", "create", "quick task", "--no-wait"])
        assert result.exit_code == 0
        assert "Created" in result.output
        container.execute_task.execute.assert_not_called()

    def test_list_empty(self) -> None:
        result = runner.invoke(app, ["task", "list"])
        assert result.exit_code == 0
        assert "No tasks" in result.output

    def test_list_populated(self, container: _MockContainer) -> None:
        task_a = _make_task("task A")
        task_b = _make_task("task B")
        container.task_repo._store[task_a.id] = task_a
        container.task_repo._store[task_b.id] = task_b

        result = runner.invoke(app, ["task", "list"])
        assert result.exit_code == 0
        assert "task A" in result.output
        assert "task B" in result.output

    def test_show_found(self, container: _MockContainer) -> None:
        task = _make_task("detail task")
        container.task_repo._store[task.id] = task

        result = runner.invoke(app, ["task", "show", task.id])
        assert result.exit_code == 0
        assert "detail task" in result.output

    def test_show_not_found(self) -> None:
        result = runner.invoke(app, ["task", "show", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_cancel_found(self, container: _MockContainer) -> None:
        task = _make_task("cancel me")
        container.task_repo._store[task.id] = task

        result = runner.invoke(app, ["task", "cancel", task.id])
        assert result.exit_code == 0
        assert "Cancelled" in result.output

        updated = container.task_repo._store.get(task.id)
        assert updated is not None
        assert updated.status == TaskStatus.FAILED

    def test_cancel_not_found(self) -> None:
        result = runner.invoke(app, ["task", "cancel", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_create_and_execute(self, container: _MockContainer) -> None:
        created = _make_task("full flow")
        executed = _make_task(
            "full flow",
            status=TaskStatus.SUCCESS,
            subtasks=[SubTask(description="step 1", status=SubTaskStatus.SUCCESS, result="done")],
        )
        container.create_task.execute = AsyncMock(return_value=created)
        container.execute_task.execute = AsyncMock(return_value=executed)

        result = runner.invoke(app, ["task", "create", "full flow"])
        assert result.exit_code == 0
        assert "full flow" in result.output
        container.execute_task.execute.assert_called_once()


# ═══════════════════════════════════════════════════════════════
# Sprint 2.11: Model Commands
# ═══════════════════════════════════════════════════════════════


class TestModelCommands:
    def test_list_models(self) -> None:
        result = runner.invoke(app, ["model", "list"])
        assert result.exit_code == 0
        assert "qwen3:8b" in result.output

    def test_status(self) -> None:
        result = runner.invoke(app, ["model", "status"])
        assert result.exit_code == 0
        assert "Running" in result.output
        assert "qwen3:8b" in result.output

    def test_status_ollama_down(self, container: _MockContainer) -> None:
        container.ollama.is_running = AsyncMock(return_value=False)
        container.ollama.list_models = AsyncMock(return_value=[])

        result = runner.invoke(app, ["model", "status"])
        assert result.exit_code == 0
        assert "Stopped" in result.output

    def test_pull_success(self, container: _MockContainer) -> None:
        result = runner.invoke(app, ["model", "pull", "llama3:8b"])
        assert result.exit_code == 0
        assert "Pulled" in result.output

    def test_pull_failure(self, container: _MockContainer) -> None:
        container.ollama.pull_model = AsyncMock(return_value=False)

        result = runner.invoke(app, ["model", "pull", "nonexistent"])
        assert result.exit_code == 1
        assert "Failed" in result.output


# ═══════════════════════════════════════════════════════════════
# Sprint 2.11: Cost Commands
# ═══════════════════════════════════════════════════════════════


class TestCostCommands:
    def test_summary_empty(self) -> None:
        result = runner.invoke(app, ["cost", "summary"])
        assert result.exit_code == 0
        assert "$0.0000" in result.output

    def test_summary_with_records(self, container: _MockContainer) -> None:
        container.cost_repo._records.append(
            CostRecord(model="ollama/qwen3:8b", cost_usd=0.0, is_local=True)
        )
        container.cost_repo._records.append(
            CostRecord(model="claude-sonnet-4-6", cost_usd=0.05, is_local=False)
        )

        result = runner.invoke(app, ["cost", "summary"])
        assert result.exit_code == 0
        assert "$0.0500" in result.output
        assert "50%" in result.output

    def test_budget_set(self) -> None:
        result = runner.invoke(app, ["cost", "budget", "100"])
        assert result.exit_code == 0
        assert "Budget set" in result.output
        assert "$100.00" in result.output


# ═══════════════════════════════════════════════════════════════
# Sprint 2-C: Plan Commands
# ═══════════════════════════════════════════════════════════════


class TestPlanCommands:
    def test_plan_create_auto_approve(self) -> None:
        result = runner.invoke(app, ["plan", "create", "test plan", "--yes"])
        assert result.exit_code == 0
        assert "Plan approved" in result.output

    def test_plan_list_empty(self) -> None:
        result = runner.invoke(app, ["plan", "list"])
        assert result.exit_code == 0
        assert "No plans" in result.output

    def test_plan_list_populated(self, container: _MockContainer) -> None:
        # Create a plan first
        from domain.entities.plan import ExecutionPlan, PlanStep

        plan = ExecutionPlan(
            goal="listed plan",
            steps=[PlanStep(subtask_description="step 1")],
        )
        container.plan_repo._store[plan.id] = plan

        result = runner.invoke(app, ["plan", "list"])
        assert result.exit_code == 0
        assert "listed plan" in result.output

    def test_plan_show_not_found(self) -> None:
        result = runner.invoke(app, ["plan", "show", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output
