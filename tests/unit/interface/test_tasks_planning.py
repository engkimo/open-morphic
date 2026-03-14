"""Tests for plan-first task flow — Sprint 9.4."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from domain.entities.plan import ExecutionPlan, PlanStep
from domain.entities.task import SubTask, TaskEntity
from domain.value_objects.status import PlanStatus
from interface.api.routes.tasks import router
from shared.config import PlanningMode, Settings


def _make_app(
    planning_mode: PlanningMode = PlanningMode.INTERACTIVE,
    auto_approve_simple: bool = True,
) -> tuple[FastAPI, SimpleNamespace]:
    """Create test app with mocked container."""
    app = FastAPI()
    app.include_router(router)

    settings = Settings(
        planning_mode=planning_mode,
        planning_auto_approve_simple=auto_approve_simple,
    )

    plan = ExecutionPlan(
        goal="FizzBuzz",
        steps=[
            PlanStep(
                subtask_description="Write FizzBuzz",
                proposed_model="ollama/qwen3:8b",
                estimated_cost_usd=0.0,
                estimated_tokens=100,
            )
        ],
        total_estimated_cost_usd=0.0,
        status=PlanStatus.PROPOSED,
    )

    task = TaskEntity(goal="FizzBuzz", subtasks=[SubTask(description="FizzBuzz")])

    interactive_plan = AsyncMock()
    interactive_plan.create_plan = AsyncMock(return_value=plan)
    interactive_plan.approve_plan = AsyncMock(return_value=task)

    create_task = AsyncMock()
    create_task.execute = AsyncMock(return_value=task)

    execute_task = AsyncMock()
    execute_task.execute = AsyncMock()

    task_repo = AsyncMock()
    task_repo.list_all = AsyncMock(return_value=[task])
    task_repo.get_by_id = AsyncMock(return_value=task)
    task_repo.delete = AsyncMock()

    container = SimpleNamespace(
        settings=settings,
        interactive_plan=interactive_plan,
        create_task=create_task,
        execute_task=execute_task,
        task_repo=task_repo,
    )

    app.state.container = container
    return app, container


class TestInteractiveMode:
    """INTERACTIVE mode: POST /api/tasks returns plan for review."""

    def test_returns_plan(self) -> None:
        app, container = _make_app(PlanningMode.INTERACTIVE)
        client = TestClient(app)

        resp = client.post("/api/tasks", json={"goal": "FizzBuzz"})

        assert resp.status_code == 201
        data = resp.json()
        # Should return a plan, not a task
        assert "steps" in data
        assert "goal" in data
        assert data["status"] == "proposed"
        container.interactive_plan.create_plan.assert_called_once_with("FizzBuzz")

    def test_does_not_execute(self) -> None:
        app, container = _make_app(PlanningMode.INTERACTIVE)
        client = TestClient(app)

        client.post("/api/tasks", json={"goal": "FizzBuzz"})

        container.create_task.execute.assert_not_called()
        container.execute_task.execute.assert_not_called()


class TestDisabledMode:
    """DISABLED mode: POST /api/tasks creates and executes immediately."""

    def test_returns_task(self) -> None:
        app, container = _make_app(PlanningMode.DISABLED)
        client = TestClient(app)

        resp = client.post("/api/tasks", json={"goal": "FizzBuzz"})

        assert resp.status_code == 201
        data = resp.json()
        # Should return a task
        assert "subtasks" in data
        assert "goal" in data
        container.create_task.execute.assert_called_once_with("FizzBuzz")

    def test_does_not_create_plan(self) -> None:
        app, container = _make_app(PlanningMode.DISABLED)
        client = TestClient(app)

        client.post("/api/tasks", json={"goal": "FizzBuzz"})

        container.interactive_plan.create_plan.assert_not_called()


class TestAutoMode:
    """AUTO mode: simple tasks auto-approve, complex tasks return plan."""

    def test_simple_task_auto_approves(self) -> None:
        app, container = _make_app(PlanningMode.AUTO)
        client = TestClient(app)

        resp = client.post("/api/tasks", json={"goal": "FizzBuzz"})

        assert resp.status_code == 201
        data = resp.json()
        # Simple task → auto-approved → returns task
        assert "subtasks" in data
        container.interactive_plan.approve_plan.assert_called_once()

    def test_complex_task_returns_plan(self) -> None:
        app, container = _make_app(PlanningMode.AUTO)
        client = TestClient(app)

        resp = client.post(
            "/api/tasks",
            json={"goal": "Build REST API with auth, database, and testing"},
        )

        assert resp.status_code == 201
        data = resp.json()
        # Complex task → returns plan for review
        assert "steps" in data
        container.interactive_plan.approve_plan.assert_not_called()

    def test_auto_approve_disabled(self) -> None:
        app, container = _make_app(PlanningMode.AUTO, auto_approve_simple=False)
        client = TestClient(app)

        resp = client.post("/api/tasks", json={"goal": "FizzBuzz"})

        assert resp.status_code == 201
        data = resp.json()
        # Auto-approve disabled → always return plan
        assert "steps" in data
        container.interactive_plan.approve_plan.assert_not_called()

    def test_medium_task_returns_plan(self) -> None:
        app, container = _make_app(PlanningMode.AUTO)
        client = TestClient(app)

        resp = client.post(
            "/api/tasks",
            json={"goal": "Create a REST API endpoint with unit tests"},
        )

        assert resp.status_code == 201
        data = resp.json()
        # Medium task → returns plan for review
        assert "steps" in data


class TestListAndGetTasks:
    """Existing CRUD endpoints remain unchanged."""

    def test_list_tasks(self) -> None:
        app, _ = _make_app(PlanningMode.INTERACTIVE)
        client = TestClient(app)

        resp = client.get("/api/tasks")

        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_get_task(self) -> None:
        app, _ = _make_app(PlanningMode.INTERACTIVE)
        client = TestClient(app)

        resp = client.get("/api/tasks/some-id")

        assert resp.status_code == 200
        assert "goal" in resp.json()

    def test_get_task_not_found(self) -> None:
        app, container = _make_app(PlanningMode.INTERACTIVE)
        container.task_repo.get_by_id = AsyncMock(return_value=None)
        client = TestClient(app)

        resp = client.get("/api/tasks/missing")

        assert resp.status_code == 404

    def test_delete_task(self) -> None:
        app, _ = _make_app(PlanningMode.INTERACTIVE)
        client = TestClient(app)

        resp = client.delete("/api/tasks/some-id")

        assert resp.status_code == 204
