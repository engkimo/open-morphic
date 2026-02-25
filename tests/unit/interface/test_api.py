"""Tests for FastAPI endpoints — Sprint 1.6.

Uses TestClient + mock AppContainer (mock LLM, real in-memory repos).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from domain.entities.cost import CostRecord
from domain.entities.task import SubTask, TaskEntity
from domain.ports.llm_gateway import LLMResponse
from domain.value_objects.status import SubTaskStatus, TaskStatus
from infrastructure.llm.cost_tracker import CostTracker
from infrastructure.memory.memory_hierarchy import MemoryHierarchy
from infrastructure.persistence.in_memory import (
    InMemoryCostRepository,
    InMemoryMemoryRepository,
    InMemoryTaskRepository,
)
from interface.api.main import create_app


# ── Mock container ──


class _MockContainer:
    """Lightweight DI container with mock LLM for testing."""

    def __init__(self) -> None:
        self.settings = _FakeSettings()
        self.task_repo = InMemoryTaskRepository()
        self.cost_repo = InMemoryCostRepository()
        self.memory_repo = InMemoryMemoryRepository()
        self.memory = MemoryHierarchy(memory_repo=self.memory_repo)

        # Mock LLM-dependent services
        self.ollama = AsyncMock()
        self.ollama.is_running = AsyncMock(return_value=True)

        self.llm = AsyncMock()
        self.llm.list_models = AsyncMock(return_value=["qwen3:8b", "qwen3-coder:30b"])

        self.cost_tracker = CostTracker(self.cost_repo)

        self.create_task = AsyncMock()
        self.execute_task = AsyncMock()


class _FakeSettings:
    ollama_default_model: str = "qwen3:8b"
    default_monthly_budget_usd: float = 50.0


@pytest.fixture()
def container() -> _MockContainer:
    return _MockContainer()


@pytest.fixture()
def client(container: _MockContainer) -> TestClient:
    app = create_app(container=container)
    return TestClient(app)


def _make_task(
    goal: str = "test goal",
    status: TaskStatus = TaskStatus.PENDING,
    subtasks: list[SubTask] | None = None,
) -> TaskEntity:
    return TaskEntity(goal=goal, status=status, subtasks=subtasks or [])


# ═══════════════════════════════════════════════════════════════
# Task CRUD
# ═══════════════════════════════════════════════════════════════


class TestTaskEndpoints:
    def test_create_task(self, client: TestClient, container: _MockContainer) -> None:
        task = _make_task("build fibonacci")
        container.create_task.execute = AsyncMock(return_value=task)
        container.execute_task.execute = AsyncMock(return_value=task)

        resp = client.post("/api/tasks", json={"goal": "build fibonacci"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["goal"] == "build fibonacci"
        assert data["status"] == "pending"
        assert "id" in data

    def test_create_task_empty_goal(self, client: TestClient) -> None:
        resp = client.post("/api/tasks", json={"goal": ""})
        assert resp.status_code == 422

    def test_list_tasks_empty(self, client: TestClient) -> None:
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tasks"] == []
        assert data["count"] == 0

    async def test_list_tasks_with_data(
        self, client: TestClient, container: _MockContainer
    ) -> None:
        task = _make_task("my task")
        await container.task_repo.save(task)
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["tasks"][0]["goal"] == "my task"

    async def test_get_task_found(
        self, client: TestClient, container: _MockContainer
    ) -> None:
        task = _make_task("specific task")
        await container.task_repo.save(task)
        resp = client.get(f"/api/tasks/{task.id}")
        assert resp.status_code == 200
        assert resp.json()["goal"] == "specific task"

    def test_get_task_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/tasks/nonexistent")
        assert resp.status_code == 404

    async def test_delete_task(
        self, client: TestClient, container: _MockContainer
    ) -> None:
        task = _make_task("to delete")
        await container.task_repo.save(task)
        resp = client.delete(f"/api/tasks/{task.id}")
        assert resp.status_code == 204
        assert await container.task_repo.get_by_id(task.id) is None

    def test_delete_task_not_found(self, client: TestClient) -> None:
        resp = client.delete("/api/tasks/nonexistent")
        assert resp.status_code == 404

    def test_task_response_includes_subtasks(
        self, client: TestClient, container: _MockContainer
    ) -> None:
        subtasks = [
            SubTask(description="step 1", status=SubTaskStatus.SUCCESS, result="done"),
            SubTask(description="step 2", status=SubTaskStatus.PENDING),
        ]
        task = _make_task("with subtasks", subtasks=subtasks)
        container.create_task.execute = AsyncMock(return_value=task)
        container.execute_task.execute = AsyncMock(return_value=task)

        resp = client.post("/api/tasks", json={"goal": "with subtasks"})
        data = resp.json()
        assert len(data["subtasks"]) == 2
        assert data["subtasks"][0]["status"] == "success"
        assert data["subtasks"][0]["result"] == "done"
        assert data["is_complete"] is False
        assert data["success_rate"] == pytest.approx(0.5)


# ═══════════════════════════════════════════════════════════════
# Model status
# ═══════════════════════════════════════════════════════════════


class TestModelEndpoints:
    def test_list_models(self, client: TestClient) -> None:
        resp = client.get("/api/models")
        assert resp.status_code == 200
        assert "qwen3:8b" in resp.json()

    def test_model_status(self, client: TestClient) -> None:
        resp = client.get("/api/models/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ollama_running"] is True
        assert data["default_model"] == "qwen3:8b"
        assert len(data["models"]) == 2

    def test_model_status_ollama_down(
        self, client: TestClient, container: _MockContainer
    ) -> None:
        container.ollama.is_running = AsyncMock(return_value=False)
        resp = client.get("/api/models/status")
        data = resp.json()
        assert data["ollama_running"] is False
        assert data["models"] == []


# ═══════════════════════════════════════════════════════════════
# Cost
# ═══════════════════════════════════════════════════════════════


class TestCostEndpoints:
    def test_cost_summary_empty(self, client: TestClient) -> None:
        resp = client.get("/api/cost")
        assert resp.status_code == 200
        data = resp.json()
        assert data["daily_total_usd"] == 0.0
        assert data["monthly_total_usd"] == 0.0
        assert data["local_usage_rate"] == 0.0
        assert data["monthly_budget_usd"] == 50.0
        assert data["budget_remaining_usd"] == 50.0

    async def test_cost_summary_with_records(
        self, client: TestClient, container: _MockContainer
    ) -> None:
        await container.cost_repo.save(
            CostRecord(model="ollama/qwen3:8b", cost_usd=0.0, is_local=True)
        )
        await container.cost_repo.save(
            CostRecord(model="claude-sonnet-4-6", cost_usd=0.01, is_local=False)
        )
        resp = client.get("/api/cost")
        data = resp.json()
        assert data["daily_total_usd"] == pytest.approx(0.01)
        assert data["local_usage_rate"] == pytest.approx(0.5)

    async def test_cost_logs(
        self, client: TestClient, container: _MockContainer
    ) -> None:
        await container.cost_repo.save(
            CostRecord(model="ollama/qwen3:8b", cost_usd=0.0, is_local=True)
        )
        resp = client.get("/api/cost/logs")
        data = resp.json()
        assert data["count"] == 1
        assert data["logs"][0]["model"] == "ollama/qwen3:8b"


# ═══════════════════════════════════════════════════════════════
# Memory
# ═══════════════════════════════════════════════════════════════


class TestMemoryEndpoints:
    def test_search_empty(self, client: TestClient) -> None:
        resp = client.get("/api/memory/search", params={"q": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "test"
        assert data["results"] == []
        assert data["count"] == 0

    async def test_search_with_data(
        self, client: TestClient, container: _MockContainer
    ) -> None:
        await container.memory.add("Python is great for data science")
        resp = client.get("/api/memory/search", params={"q": "Python"})
        data = resp.json()
        assert data["count"] >= 1
        assert any("Python" in r for r in data["results"])


# ═══════════════════════════════════════════════════════════════
# WebSocket
# ═══════════════════════════════════════════════════════════════


class TestWebSocket:
    async def test_ws_task_not_found(
        self, client: TestClient,
    ) -> None:
        with client.websocket_connect("/ws/tasks/nonexistent") as ws:
            data = ws.receive_json()
            assert "error" in data

    async def test_ws_sends_task_snapshot(
        self, client: TestClient, container: _MockContainer
    ) -> None:
        task = _make_task(
            "ws test",
            status=TaskStatus.SUCCESS,
            subtasks=[SubTask(description="s1", status=SubTaskStatus.SUCCESS)],
        )
        await container.task_repo.save(task)
        with client.websocket_connect(f"/ws/tasks/{task.id}") as ws:
            data = ws.receive_json()
            assert data["goal"] == "ws test"
            assert data["is_complete"] is True

    async def test_ws_stops_on_complete(
        self, client: TestClient, container: _MockContainer
    ) -> None:
        task = _make_task(
            "done task",
            status=TaskStatus.SUCCESS,
            subtasks=[SubTask(description="s1", status=SubTaskStatus.SUCCESS)],
        )
        await container.task_repo.save(task)
        with client.websocket_connect(f"/ws/tasks/{task.id}") as ws:
            data = ws.receive_json()
            assert data["is_complete"] is True
            # Connection should close after complete task


# ═══════════════════════════════════════════════════════════════
# App lifecycle & CORS
# ═══════════════════════════════════════════════════════════════


class TestApp:
    def test_health(self, client: TestClient) -> None:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_cors_headers(self, client: TestClient) -> None:
        resp = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
