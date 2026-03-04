"""Tests for Engine API endpoints — Sprint 4.3."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from application.use_cases.route_to_engine import RouteToEngineUseCase
from domain.ports.agent_engine import AgentEngineCapabilities, AgentEnginePort, AgentEngineResult
from domain.value_objects.agent_engine import AgentEngineType
from interface.api.main import create_app


def _make_driver(
    engine_type: AgentEngineType = AgentEngineType.OLLAMA,
    available: bool = True,
    max_context_tokens: int = 8_000,
    cost_per_hour_usd: float = 0.0,
) -> AsyncMock:
    driver = AsyncMock(spec=AgentEnginePort)
    driver.is_available = AsyncMock(return_value=available)
    driver.get_capabilities.return_value = AgentEngineCapabilities(
        engine_type=engine_type,
        max_context_tokens=max_context_tokens,
        cost_per_hour_usd=cost_per_hour_usd,
    )
    driver.run_task = AsyncMock(
        return_value=AgentEngineResult(
            engine=engine_type,
            success=True,
            output="done",
            cost_usd=0.0,
        )
    )
    return driver


class _MockContainer:
    """Minimal container for engine endpoint tests."""

    def __init__(self) -> None:
        drivers: dict[AgentEngineType, AgentEnginePort] = {
            AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA),
            AgentEngineType.CLAUDE_CODE: _make_driver(
                AgentEngineType.CLAUDE_CODE,
                available=False,
                max_context_tokens=200_000,
                cost_per_hour_usd=3.0,
            ),
        }
        self.route_to_engine = RouteToEngineUseCase(drivers)
        self.agent_drivers = drivers


@pytest.fixture()
def container() -> _MockContainer:
    return _MockContainer()


@pytest.fixture()
def client(container: _MockContainer) -> TestClient:
    app = create_app(container=container)
    return TestClient(app)


class TestListEngines:
    def test_list_returns_all(self, client: TestClient) -> None:
        resp = client.get("/api/engines")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        types = {e["engine_type"] for e in data["engines"]}
        assert "ollama" in types
        assert "claude_code" in types

    def test_list_shows_availability(self, client: TestClient) -> None:
        resp = client.get("/api/engines")
        data = resp.json()
        by_type = {e["engine_type"]: e for e in data["engines"]}
        assert by_type["ollama"]["available"] is True
        assert by_type["claude_code"]["available"] is False

    def test_list_shows_capabilities(self, client: TestClient) -> None:
        resp = client.get("/api/engines")
        data = resp.json()
        by_type = {e["engine_type"]: e for e in data["engines"]}
        assert by_type["claude_code"]["max_context_tokens"] == 200_000
        assert by_type["claude_code"]["cost_per_hour_usd"] == 3.0
        assert by_type["ollama"]["cost_per_hour_usd"] == 0.0


class TestGetEngine:
    def test_get_found(self, client: TestClient) -> None:
        resp = client.get("/api/engines/ollama")
        assert resp.status_code == 200
        data = resp.json()
        assert data["engine_type"] == "ollama"
        assert data["available"] is True

    def test_get_unknown_engine(self, client: TestClient) -> None:
        resp = client.get("/api/engines/nonexistent")
        assert resp.status_code == 404

    def test_get_unregistered_engine(self, client: TestClient) -> None:
        resp = client.get("/api/engines/gemini_cli")
        assert resp.status_code == 404


class TestRunEngine:
    def test_run_auto_route(self, client: TestClient) -> None:
        resp = client.post("/api/engines/run", json={"task": "Hello world"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["engine"] == "ollama"

    def test_run_with_engine_override(self, client: TestClient, container: _MockContainer) -> None:
        # Make claude_code available for this test
        container.agent_drivers[AgentEngineType.CLAUDE_CODE].is_available = AsyncMock(
            return_value=True
        )
        resp = client.post(
            "/api/engines/run",
            json={"task": "Analyze code", "engine": "claude_code", "budget": 5.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["engine"] == "claude_code"

    def test_run_unknown_engine_400(self, client: TestClient) -> None:
        resp = client.post(
            "/api/engines/run",
            json={"task": "Test", "engine": "nonexistent"},
        )
        assert resp.status_code == 400

    def test_run_unknown_task_type_400(self, client: TestClient) -> None:
        resp = client.post(
            "/api/engines/run",
            json={"task": "Test", "task_type": "invalid_type"},
        )
        assert resp.status_code == 400

    def test_run_empty_task_422(self, client: TestClient) -> None:
        resp = client.post("/api/engines/run", json={"task": ""})
        assert resp.status_code == 422

    def test_run_includes_cost_and_duration(self, client: TestClient) -> None:
        resp = client.post("/api/engines/run", json={"task": "Quick question"})
        data = resp.json()
        assert "cost_usd" in data
        assert "duration_seconds" in data
