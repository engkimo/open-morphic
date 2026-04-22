"""Tests for Cost API endpoints — TD-147."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from domain.entities.cost import CostRecord
from interface.api.main import create_app
from shared.config import Settings


class _MockCostRepo:
    def __init__(self) -> None:
        self.get_daily_total = AsyncMock(return_value=1.25)
        self.get_monthly_total = AsyncMock(return_value=12.50)
        self.get_local_usage_rate = AsyncMock(return_value=0.85)
        self.list_recent = AsyncMock(return_value=[
            CostRecord(
                task_id="t-1",
                model="ollama/qwen3:8b",
                cost_usd=0.0,
                input_tokens=100,
                output_tokens=50,
                created_at=datetime.now(UTC),
            ),
        ])


class _MockContainer:
    def __init__(self) -> None:
        self.settings = Settings(default_monthly_budget_usd=50.0)
        self.cost_repo = _MockCostRepo()


@pytest.fixture()
def client() -> TestClient:
    app = create_app(container=_MockContainer())
    return TestClient(app)


class TestCostSummary:
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/api/cost").status_code == 200

    def test_summary_shape(self, client: TestClient) -> None:
        data = client.get("/api/cost").json()
        assert data["daily_total_usd"] == 1.25
        assert data["monthly_total_usd"] == 12.50
        assert data["local_usage_rate"] == 0.85
        assert data["monthly_budget_usd"] == 50.0
        assert data["budget_remaining_usd"] == 37.50


class TestCostLogs:
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/api/cost/logs").status_code == 200

    def test_logs_count(self, client: TestClient) -> None:
        data = client.get("/api/cost/logs").json()
        assert data["count"] == 1
        assert data["logs"][0]["model"] == "ollama/qwen3:8b"

    def test_logs_with_limit(self, client: TestClient) -> None:
        client.get("/api/cost/logs?limit=10")
        # Just ensure parameter doesn't break
