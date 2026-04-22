"""Tests for Memory API endpoints — TD-147."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from interface.api.main import create_app
from shared.config import Settings


class _MockContextBridge:
    def __init__(self) -> None:
        self.export = AsyncMock(return_value=MagicMock(
            platform="claude_code",
            content="# Context\nTask: test",
            token_estimate=50,
        ))


class _MockMemory:
    def __init__(self) -> None:
        self.retrieve = AsyncMock(return_value="Result line 1\nResult line 2")


class _MockContainer:
    def __init__(self) -> None:
        self.settings = Settings()
        self.memory = _MockMemory()
        self.context_bridge = _MockContextBridge()


@pytest.fixture()
def client() -> TestClient:
    app = create_app(container=_MockContainer())
    return TestClient(app)


class TestSearchMemory:
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/api/memory/search?q=test").status_code == 200

    def test_results_shape(self, client: TestClient) -> None:
        data = client.get("/api/memory/search?q=test").json()
        assert data["query"] == "test"
        assert data["count"] == 2
        assert len(data["results"]) == 2

    def test_empty_result(self, client: TestClient) -> None:
        # Override retrieve to return empty
        app = client.app
        app.state.container.memory.retrieve = AsyncMock(return_value="")
        data = client.get("/api/memory/search?q=nothing").json()
        assert data["count"] == 0


class TestExportContext:
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/api/memory/export?platform=claude_code").status_code == 200

    def test_export_shape(self, client: TestClient) -> None:
        data = client.get("/api/memory/export?platform=claude_code").json()
        assert data["platform"] == "claude_code"
        assert "Context" in data["content"]
        assert data["token_estimate"] == 50

    def test_export_with_max_tokens(self, client: TestClient) -> None:
        resp = client.get("/api/memory/export?platform=chatgpt&max_tokens=200")
        assert resp.status_code == 200
