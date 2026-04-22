"""Tests for plan routes — approve triggers async execution without Celery.

Sprint 21.1 — BUG-001 fix: approve_plan must fire-and-forget task execution
even when Celery is disabled.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from application.use_cases.interactive_plan import PlanAlreadyDecidedError, PlanNotFoundError
from domain.entities.plan import ExecutionPlan, PlanStep
from domain.entities.task import SubTask, TaskEntity
from domain.value_objects.status import PlanStatus
from interface.api.routes.plans import router
from shared.config import Settings


def _make_app(celery_enabled: bool = False) -> tuple[FastAPI, SimpleNamespace]:
    """Create test app with mocked container for plan routes."""
    app = FastAPI()
    app.include_router(router)

    plan = ExecutionPlan(
        goal="Test goal",
        steps=[
            PlanStep(
                subtask_description="Do something",
                proposed_model="ollama/qwen3:8b",
                estimated_cost_usd=0.0,
                estimated_tokens=100,
            )
        ],
        total_estimated_cost_usd=0.0,
        status=PlanStatus.PROPOSED,
    )

    task = TaskEntity(goal="Test goal", subtasks=[SubTask(description="Do something")])

    interactive_plan = AsyncMock()
    interactive_plan.create_plan = AsyncMock(return_value=plan)
    interactive_plan.approve_plan = AsyncMock(return_value=task)
    interactive_plan.reject_plan = AsyncMock(return_value=plan)

    execute_task = AsyncMock()
    execute_task.execute = AsyncMock()

    plan_repo = AsyncMock()
    plan_repo.list_all = AsyncMock(return_value=[plan])
    plan_repo.get_by_id = AsyncMock(return_value=plan)

    settings = Settings(celery_enabled=celery_enabled)

    container = SimpleNamespace(
        settings=settings,
        interactive_plan=interactive_plan,
        execute_task=execute_task,
        plan_repo=plan_repo,
    )

    app.state.container = container
    return app, container


class TestCreatePlan:
    """POST /api/plans creates an execution plan."""

    def test_creates_plan(self) -> None:
        app, container = _make_app()
        client = TestClient(app)

        resp = client.post("/api/plans", json={"goal": "Test goal"})

        assert resp.status_code == 201
        data = resp.json()
        assert "steps" in data
        assert data["goal"] == "Test goal"
        container.interactive_plan.create_plan.assert_called_once()

    def test_creates_plan_with_model(self) -> None:
        app, container = _make_app()
        client = TestClient(app)

        resp = client.post("/api/plans", json={"goal": "Test", "model": "claude-sonnet-4-6"})

        assert resp.status_code == 201
        container.interactive_plan.create_plan.assert_called_once_with(
            "Test", model="claude-sonnet-4-6"
        )


class TestListPlans:
    """GET /api/plans lists all plans."""

    def test_list_plans(self) -> None:
        app, _ = _make_app()
        client = TestClient(app)

        resp = client.get("/api/plans")

        assert resp.status_code == 200
        assert resp.json()["count"] == 1


class TestGetPlan:
    """GET /api/plans/{id} returns a specific plan."""

    def test_get_existing(self) -> None:
        app, _ = _make_app()
        client = TestClient(app)

        resp = client.get("/api/plans/some-id")

        assert resp.status_code == 200
        assert "steps" in resp.json()

    def test_get_not_found(self) -> None:
        app, container = _make_app()
        container.plan_repo.get_by_id = AsyncMock(return_value=None)
        client = TestClient(app)

        resp = client.get("/api/plans/missing")

        assert resp.status_code == 404


class TestApprovePlan:
    """POST /api/plans/{id}/approve triggers task execution."""

    @patch("interface.api.routes.plans.asyncio.create_task")
    def test_approve_returns_task(self, mock_create_task) -> None:
        mock_create_task.side_effect = lambda coro: (coro.close(), MagicMock())[1]
        app, container = _make_app()
        client = TestClient(app)

        resp = client.post("/api/plans/some-id/approve")

        assert resp.status_code == 200
        data = resp.json()
        assert "subtasks" in data
        container.interactive_plan.approve_plan.assert_called_once_with("some-id")

    @patch("interface.api.routes.plans.asyncio.create_task")
    def test_approve_triggers_async_execution_without_celery(self, mock_create_task) -> None:
        mock_create_task.side_effect = lambda coro: (coro.close(), MagicMock())[1]
        """BUG-001 fix: approve must trigger execution even without Celery."""
        app, container = _make_app(celery_enabled=False)
        client = TestClient(app)

        client.post("/api/plans/plan-123/approve")

        # asyncio.create_task must be called with a coroutine
        mock_create_task.assert_called_once()

    def test_approve_not_found(self) -> None:
        app, container = _make_app()
        container.interactive_plan.approve_plan.side_effect = PlanNotFoundError("not found")
        client = TestClient(app)

        resp = client.post("/api/plans/missing/approve")

        assert resp.status_code == 404

    def test_approve_already_decided(self) -> None:
        app, container = _make_app()
        container.interactive_plan.approve_plan.side_effect = PlanAlreadyDecidedError(
            "decided", "approved"
        )
        client = TestClient(app)

        resp = client.post("/api/plans/decided/approve")

        assert resp.status_code == 409


class TestRejectPlan:
    """POST /api/plans/{id}/reject rejects a plan."""

    def test_reject_returns_plan(self) -> None:
        app, container = _make_app()
        client = TestClient(app)

        resp = client.post("/api/plans/some-id/reject")

        assert resp.status_code == 200
        data = resp.json()
        assert "steps" in data
        container.interactive_plan.reject_plan.assert_called_once_with("some-id")

    def test_reject_not_found(self) -> None:
        app, container = _make_app()
        container.interactive_plan.reject_plan.side_effect = PlanNotFoundError("not found")
        client = TestClient(app)

        resp = client.post("/api/plans/missing/reject")

        assert resp.status_code == 404

    def test_reject_already_decided(self) -> None:
        app, container = _make_app()
        container.interactive_plan.reject_plan.side_effect = PlanAlreadyDecidedError(
            "decided", "rejected"
        )
        client = TestClient(app)

        resp = client.post("/api/plans/decided/reject")

        assert resp.status_code == 409
