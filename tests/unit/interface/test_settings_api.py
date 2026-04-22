"""Tests for Settings API endpoints — TD-146."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from interface.api.main import create_app
from shared.config import Settings


class _MockContainer:
    """Minimal container for settings endpoint tests."""

    def __init__(self) -> None:
        self.settings = Settings(
            morphic_agent_env="development",
            planning_mode="interactive",
            local_first=True,
            anthropic_api_key="sk-ant-xxx",
            openai_api_key="",
            google_gemini_api_key="gemini-key",
            ollama_base_url="http://127.0.0.1:11434",
            ollama_default_model="qwen3:8b",
            default_monthly_budget_usd=50.0,
            default_task_budget_usd=1.0,
        )
        self.task_repo = MagicMock()


@pytest.fixture()
def container() -> _MockContainer:
    return _MockContainer()


@pytest.fixture()
def client(container: _MockContainer) -> TestClient:
    app = create_app(container=container)
    return TestClient(app)


class TestGetSettings:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/settings")
        assert resp.status_code == 200

    def test_contains_version(self, client: TestClient) -> None:
        data = client.get("/api/settings").json()
        assert data["version"] == "0.5.1"

    def test_api_keys_redacted(self, client: TestClient) -> None:
        data = client.get("/api/settings").json()
        # Keys should be booleans, not actual values
        assert data["api_keys_configured"]["anthropic"] is True
        assert data["api_keys_configured"]["openai"] is False
        assert data["api_keys_configured"]["gemini"] is True
        # Ensure no raw key value leaked
        raw = str(data)
        assert "sk-ant-xxx" not in raw
        assert "gemini-key" not in raw

    def test_budget_fields(self, client: TestClient) -> None:
        data = client.get("/api/settings").json()
        assert data["budget"]["monthly_usd"] == 50.0
        assert data["budget"]["task_usd"] == 1.0

    def test_engine_flags(self, client: TestClient) -> None:
        data = client.get("/api/settings").json()
        assert "engines" in data
        assert isinstance(data["engines"]["claude_code_enabled"], bool)

    def test_planning_mode(self, client: TestClient) -> None:
        data = client.get("/api/settings").json()
        assert data["planning_mode"] == "interactive"

    def test_local_first(self, client: TestClient) -> None:
        data = client.get("/api/settings").json()
        assert data["local_first"] is True


class TestGetHealth:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/settings/health")
        assert resp.status_code == 200

    def test_has_overall(self, client: TestClient) -> None:
        data = client.get("/api/settings/health").json()
        assert "overall" in data
        assert data["overall"] in ("ok", "degraded")

    def test_has_checks_list(self, client: TestClient) -> None:
        data = client.get("/api/settings/health").json()
        assert isinstance(data["checks"], list)
        assert len(data["checks"]) >= 2  # at least ollama + database

    def test_ollama_check_present(self, client: TestClient) -> None:
        data = client.get("/api/settings/health").json()
        names = [c["name"] for c in data["checks"]]
        assert "ollama" in names

    def test_database_check_present(self, client: TestClient) -> None:
        data = client.get("/api/settings/health").json()
        names = [c["name"] for c in data["checks"]]
        assert "database" in names


class TestGetFractalSection:
    def test_fractal_in_get_settings(self, client: TestClient) -> None:
        data = client.get("/api/settings").json()
        assert "fractal" in data
        f = data["fractal"]
        assert "max_depth" in f
        assert "candidates_per_node" in f
        assert "max_concurrent_nodes" in f
        assert "throttle_delay_ms" in f
        assert "max_total_nodes" in f
        assert "max_reflection_rounds" in f


class TestPutFractalSettings:
    def test_update_single_field(self, client: TestClient, container: _MockContainer) -> None:
        resp = client.put("/api/settings/fractal", json={"max_depth": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated"] == {"max_depth": 5}
        assert data["fractal"]["max_depth"] == 5
        # Verify the underlying settings object mutated
        assert container.settings.fractal_max_depth == 5

    def test_update_multiple_fields(self, client: TestClient, container: _MockContainer) -> None:
        resp = client.put(
            "/api/settings/fractal",
            json={"max_concurrent_nodes": 2, "throttle_delay_ms": 500},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated"]["max_concurrent_nodes"] == 2
        assert data["updated"]["throttle_delay_ms"] == 500
        assert container.settings.fractal_max_concurrent_nodes == 2
        assert container.settings.fractal_throttle_delay_ms == 500

    def test_null_fields_ignored(self, client: TestClient, container: _MockContainer) -> None:
        original_depth = container.settings.fractal_max_depth
        resp = client.put("/api/settings/fractal", json={"max_depth": None})
        assert resp.status_code == 200
        assert container.settings.fractal_max_depth == original_depth

    def test_empty_body_no_changes(self, client: TestClient) -> None:
        resp = client.put("/api/settings/fractal", json={})
        assert resp.status_code == 200
        assert resp.json()["updated"] == {}

    def test_validation_rejects_out_of_range(self, client: TestClient) -> None:
        resp = client.put("/api/settings/fractal", json={"max_depth": 99})
        assert resp.status_code == 422
