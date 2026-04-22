"""API E2E Tests — HTTP round-trip through FastAPI endpoints.

Tests the full flow: POST /api/tasks → background execution → GET verification.
Uses a mock container where create_task and execute_task simulate real behavior
with in-memory repos (no LLM calls).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from domain.entities.cost import CostRecord
from domain.entities.task import SubTask, TaskEntity
from domain.value_objects.status import SubTaskStatus, TaskStatus
from infrastructure.llm.cost_tracker import CostTracker
from infrastructure.memory.memory_hierarchy import MemoryHierarchy
from infrastructure.persistence.in_memory import (
    InMemoryCostRepository,
    InMemoryMemoryRepository,
    InMemoryTaskRepository,
)
from interface.api.main import create_app
from shared.config import PlanningMode


class _FakeSettings:
    ollama_default_model: str = "qwen3:8b"
    default_monthly_budget_usd: float = 50.0
    default_task_budget_usd: float = 1.0
    affinity_min_samples: int = 3
    affinity_boost_threshold: float = 0.6
    celery_enabled: bool = False
    planning_mode: PlanningMode = PlanningMode.DISABLED
    planning_auto_approve_simple: bool = True
    # ReAct (Phase 12)
    react_enabled: bool = False
    react_max_iterations: int = 10
    # LAEE
    laee_approval_mode: str = "confirm-destructive"
    laee_audit_log_path: Path = Path("/tmp/morphic_test_audit.jsonl")
    laee_undo_enabled: bool = False


class _E2EContainer:
    """Container that simulates real create+execute behavior with in-memory state."""

    def __init__(self) -> None:
        self.settings = _FakeSettings()
        self.task_repo = InMemoryTaskRepository()
        self.cost_repo = InMemoryCostRepository()
        self.memory_repo = InMemoryMemoryRepository()
        self.memory = MemoryHierarchy(memory_repo=self.memory_repo)

        self.ollama = AsyncMock()
        self.ollama.is_running = AsyncMock(return_value=True)

        self.llm = AsyncMock()
        self.llm.list_models = AsyncMock(return_value=["qwen3:8b"])

        self.cost_tracker = CostTracker(self.cost_repo)

        # create_task: simulate decomposition → save to repo
        self.create_task = AsyncMock()
        self.create_task.execute = AsyncMock(side_effect=self._create_task)

        # execute_task: simulate DAG execution → update repo
        self.execute_task = AsyncMock()
        self.execute_task.execute = AsyncMock(side_effect=self._execute_task)

    async def _create_task(self, goal: str) -> TaskEntity:
        task = TaskEntity(
            goal=goal,
            subtasks=[
                SubTask(id="s1", description=f"Analyze: {goal}"),
                SubTask(id="s2", description=f"Implement: {goal}", dependencies=["s1"]),
            ],
        )
        await self.task_repo.save(task)
        return task

    async def _execute_task(self, task_id: str, **_kwargs) -> TaskEntity:
        task = await self.task_repo.get_by_id(task_id)
        assert task is not None

        task.status = TaskStatus.RUNNING
        await self.task_repo.update(task)

        # Simulate subtask execution
        for st in task.subtasks:
            st.status = SubTaskStatus.SUCCESS
            st.result = f"Completed: {st.description}"
            st.model_used = "qwen3:8b"
            st.cost_usd = 0.0

        task.status = TaskStatus.SUCCESS
        task.total_cost_usd = 0.0
        await self.task_repo.update(task)
        return task


@pytest.fixture()
def container() -> _E2EContainer:
    return _E2EContainer()


@pytest.fixture()
def client(container: _E2EContainer) -> TestClient:
    app = create_app(container=container)
    return TestClient(app)


class TestAPIEndToEnd:
    """Full HTTP round-trip: POST → background execute → GET → verify."""

    def test_create_task_returns_201_with_subtasks(
        self, client: TestClient, container: _E2EContainer
    ) -> None:
        resp = client.post("/api/tasks", json={"goal": "Build a REST API"})
        assert resp.status_code == 201
        data = resp.json()

        assert data["goal"] == "Build a REST API"
        assert data["status"] == "pending"
        assert len(data["subtasks"]) == 2
        assert data["subtasks"][0]["description"] == "Analyze: Build a REST API"
        assert data["subtasks"][1]["dependencies"] == ["s1"]
        assert data["is_complete"] is False

    async def test_post_then_get_shows_completed(
        self, client: TestClient, container: _E2EContainer
    ) -> None:
        """POST creates task, background execute completes, GET shows success."""
        # POST creates the task
        resp = client.post("/api/tasks", json={"goal": "Implement auth"})
        assert resp.status_code == 201
        task_id = resp.json()["id"]

        # Background execution is triggered by BackgroundTasks
        # TestClient runs background tasks synchronously before response is complete
        # So by the time we GET, execution should be done

        # Verify execution was triggered
        container.execute_task.execute.assert_called_once()
        call_args = container.execute_task.execute.call_args
        assert call_args[0][0] == task_id  # first positional arg is task_id

        # Wait a tiny bit for background task to complete if needed
        await asyncio.sleep(0.01)

        # GET should show completed task
        resp = client.get(f"/api/tasks/{task_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == task_id
        assert data["status"] == "success"
        assert data["is_complete"] is True
        assert data["success_rate"] == 1.0
        assert all(s["status"] == "success" for s in data["subtasks"])

    async def test_list_tasks_after_creation(
        self, client: TestClient, container: _E2EContainer
    ) -> None:
        """Created tasks appear in GET /api/tasks list."""
        # Create two tasks
        client.post("/api/tasks", json={"goal": "Task Alpha"})
        client.post("/api/tasks", json={"goal": "Task Beta"})

        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        goals = {t["goal"] for t in data["tasks"]}
        assert goals == {"Task Alpha", "Task Beta"}

    async def test_delete_after_execution(
        self, client: TestClient, container: _E2EContainer
    ) -> None:
        """Create → execute → delete → verify gone."""
        resp = client.post("/api/tasks", json={"goal": "To be deleted"})
        task_id = resp.json()["id"]

        # Verify exists
        resp = client.get(f"/api/tasks/{task_id}")
        assert resp.status_code == 200

        # Delete
        resp = client.delete(f"/api/tasks/{task_id}")
        assert resp.status_code == 204

        # Verify gone
        resp = client.get(f"/api/tasks/{task_id}")
        assert resp.status_code == 404

        # Verify list is empty
        resp = client.get("/api/tasks")
        assert resp.json()["count"] == 0


class TestAPIEndToEndFailure:
    """Failure paths through the API."""

    def test_create_task_empty_goal_422(self, client: TestClient) -> None:
        resp = client.post("/api/tasks", json={"goal": ""})
        assert resp.status_code == 422

    def test_create_task_missing_goal_422(self, client: TestClient) -> None:
        resp = client.post("/api/tasks", json={})
        assert resp.status_code == 422

    def test_get_nonexistent_task_404(self, client: TestClient) -> None:
        resp = client.get("/api/tasks/nonexistent-id")
        assert resp.status_code == 404

    def test_delete_nonexistent_task_404(self, client: TestClient) -> None:
        resp = client.delete("/api/tasks/nonexistent-id")
        assert resp.status_code == 404


class TestAPIEndToEndCostTracking:
    """Cost endpoints after task execution."""

    async def test_cost_summary_reflects_execution(
        self, client: TestClient, container: _E2EContainer
    ) -> None:
        """Cost summary reflects records added during execution."""
        # Add cost records as if execution happened
        await container.cost_repo.save(
            CostRecord(model="ollama/qwen3:8b", cost_usd=0.0, is_local=True)
        )
        await container.cost_repo.save(
            CostRecord(model="ollama/qwen3:8b", cost_usd=0.0, is_local=True)
        )

        resp = client.get("/api/cost")
        assert resp.status_code == 200
        data = resp.json()
        assert data["daily_total_usd"] == 0.0
        assert data["local_usage_rate"] == 1.0
        assert data["budget_remaining_usd"] == 50.0

    async def test_cost_logs_contain_records(
        self, client: TestClient, container: _E2EContainer
    ) -> None:
        await container.cost_repo.save(
            CostRecord(model="claude-haiku-4-5", cost_usd=0.003, is_local=False)
        )

        resp = client.get("/api/cost/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["logs"][0]["model"] == "claude-haiku-4-5"
        assert data["logs"][0]["is_local"] is False


class TestAPIEndToEndWebSocket:
    """WebSocket endpoint integration."""

    async def test_ws_reflects_completed_task(
        self, client: TestClient, container: _E2EContainer
    ) -> None:
        """WebSocket sends completed task snapshot."""
        # Create and "execute" a task through the API
        resp = client.post("/api/tasks", json={"goal": "WS test"})
        task_id = resp.json()["id"]

        # WebSocket should see completed state
        with client.websocket_connect(f"/ws/tasks/{task_id}") as ws:
            data = ws.receive_json()
            assert data["id"] == task_id
            assert data["is_complete"] is True
            assert data["status"] == "success"

    async def test_ws_nonexistent_task_error(self, client: TestClient) -> None:
        with client.websocket_connect("/ws/tasks/doesnt-exist") as ws:
            data = ws.receive_json()
            assert "error" in data
