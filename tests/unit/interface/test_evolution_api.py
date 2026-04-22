"""Tests for evolution API routes."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from domain.entities.execution_record import ExecutionRecord
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType


def _make_app():  # type: ignore[no-untyped-def]
    """Create a test app with a minimal container."""
    from application.use_cases.analyze_execution import AnalyzeExecutionUseCase
    from application.use_cases.systemic_evolution import SystemicEvolutionUseCase
    from application.use_cases.update_strategy import UpdateStrategyUseCase
    from infrastructure.evolution.strategy_store import StrategyStore
    from infrastructure.persistence.in_memory_execution_record import (
        InMemoryExecutionRecordRepository,
    )
    from interface.api.main import create_app

    class TestContainer:
        def __init__(self) -> None:
            self.execution_repo = InMemoryExecutionRecordRepository()
            self.strategy_store = StrategyStore(base_dir=Path(tempfile.mkdtemp()))
            self.analyze_execution = AnalyzeExecutionUseCase(repo=self.execution_repo)
            self.update_strategy = UpdateStrategyUseCase(
                execution_repo=self.execution_repo,
                strategy_store=self.strategy_store,
                min_samples=2,
            )
            self.systemic_evolution = SystemicEvolutionUseCase(
                analyze_execution=self.analyze_execution,
                update_strategy=self.update_strategy,
                discover_tools=None,
            )

    container = TestContainer()
    app = create_app(container=container)
    return app, container


def _rec(
    success: bool = True,
    error: str | None = None,
    model: str = "ollama/qwen3:8b",
    engine: AgentEngineType = AgentEngineType.OLLAMA,
    task_type: TaskType = TaskType.SIMPLE_QA,
) -> ExecutionRecord:
    return ExecutionRecord(
        task_id="t1",
        task_type=task_type,
        engine_used=engine,
        model_used=model,
        success=success,
        error_message=error,
        cost_usd=0.01,
        duration_seconds=1.0,
    )


class TestEvolutionAPI:
    def setup_method(self) -> None:
        self.app, self.container = _make_app()
        self.client = TestClient(self.app)

    def test_get_stats_empty(self) -> None:
        resp = self.client.get("/api/evolution/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 0

    @pytest.mark.asyncio
    async def test_get_stats_with_data(self) -> None:
        await self.container.execution_repo.save(_rec(success=True))
        await self.container.execution_repo.save(_rec(success=False, error="err"))
        resp = self.client.get("/api/evolution/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 2
        assert data["success_count"] == 1

    def test_get_stats_with_task_type_filter(self) -> None:
        resp = self.client.get("/api/evolution/stats?task_type=simple_qa")
        assert resp.status_code == 200

    def test_get_failures_empty(self) -> None:
        resp = self.client.get("/api/evolution/failures")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_get_failures_with_data(self) -> None:
        await self.container.execution_repo.save(_rec(success=False, error="timeout"))
        await self.container.execution_repo.save(_rec(success=False, error="timeout"))
        resp = self.client.get("/api/evolution/failures")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        assert data["patterns"][0]["count"] == 2

    def test_get_preferences_empty(self) -> None:
        resp = self.client.get("/api/evolution/preferences")
        assert resp.status_code == 200
        data = resp.json()
        assert data["model_preferences"] == []
        assert data["engine_preferences"] == []

    def test_trigger_update(self) -> None:
        resp = self.client.post("/api/evolution/update")
        assert resp.status_code == 200
        data = resp.json()
        assert "model_preferences_updated" in data

    def test_trigger_evolve(self) -> None:
        resp = self.client.post("/api/evolution/evolve")
        assert resp.status_code == 200
        data = resp.json()
        assert data["level"] == "systemic"
        assert "summary" in data

    @pytest.mark.asyncio
    async def test_evolve_with_data(self) -> None:
        for _ in range(5):
            await self.container.execution_repo.save(_rec(success=True))
        resp = self.client.post("/api/evolution/evolve")
        assert resp.status_code == 200
        data = resp.json()
        assert data["level"] == "systemic"

    @pytest.mark.asyncio
    async def test_update_creates_preferences(self) -> None:
        for _ in range(3):
            await self.container.execution_repo.save(_rec(model="m1", success=True))
        resp = self.client.post("/api/evolution/update")
        assert resp.status_code == 200
        data = resp.json()
        assert data["model_preferences_updated"] >= 1

    def test_get_failures_with_limit(self) -> None:
        resp = self.client.get("/api/evolution/failures?limit=5")
        assert resp.status_code == 200
