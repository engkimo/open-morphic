"""Tests for Models API endpoints — TD-147."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from interface.api.main import create_app
from shared.config import Settings


class _MockLLM:
    def __init__(self) -> None:
        self.list_models = AsyncMock(return_value=["qwen3:8b", "deepseek-r1:8b"])


class _MockOllama:
    def __init__(self) -> None:
        self.is_running = AsyncMock(return_value=True)
        self.get_running_models = AsyncMock(return_value=[
            {"name": "qwen3:8b", "size": "4.7GB"},
        ])


class _MockManageOllama:
    def __init__(self) -> None:
        self.pull = AsyncMock(return_value=True)
        self.delete = AsyncMock(return_value=True)
        self.switch_default = AsyncMock(return_value=True)
        self.info = AsyncMock(return_value={"family": "qwen3", "parameters": "8B"})


class _MockContainer:
    def __init__(self) -> None:
        self.settings = Settings(ollama_default_model="qwen3:8b")
        self.llm = _MockLLM()
        self.ollama = _MockOllama()
        self.manage_ollama = _MockManageOllama()


@pytest.fixture()
def client() -> TestClient:
    app = create_app(container=_MockContainer())
    return TestClient(app)


class TestListModels:
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/api/models").status_code == 200

    def test_returns_model_list(self, client: TestClient) -> None:
        data = client.get("/api/models").json()
        assert "qwen3:8b" in data
        assert len(data) == 2


class TestModelStatus:
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/api/models/status").status_code == 200

    def test_ollama_running(self, client: TestClient) -> None:
        data = client.get("/api/models/status").json()
        assert data["ollama_running"] is True
        assert data["default_model"] == "qwen3:8b"
        assert len(data["models"]) == 2

    def test_ollama_down(self, client: TestClient) -> None:
        app = client.app
        app.state.container.ollama.is_running = AsyncMock(return_value=False)
        data = client.get("/api/models/status").json()
        assert data["ollama_running"] is False
        assert data["models"] == []


class TestRunningModels:
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/api/models/running").status_code == 200

    def test_returns_list(self, client: TestClient) -> None:
        data = client.get("/api/models/running").json()
        assert len(data) == 1
        assert data[0]["name"] == "qwen3:8b"


class TestPullModel:
    def test_pull_success(self, client: TestClient) -> None:
        resp = client.post("/api/models/pull", json={"name": "phi4:14b"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_pull_failure(self, client: TestClient) -> None:
        app = client.app
        app.state.container.manage_ollama.pull = AsyncMock(return_value=False)
        resp = client.post("/api/models/pull", json={"name": "bad-model"})
        assert resp.status_code == 500


class TestSwitchModel:
    def test_switch_success(self, client: TestClient) -> None:
        resp = client.post("/api/models/switch", json={"name": "deepseek-r1:8b"})
        assert resp.status_code == 200
        assert resp.json()["default"] is True


class TestModelInfo:
    def test_info_found(self, client: TestClient) -> None:
        resp = client.get("/api/models/qwen3:8b/info")
        assert resp.status_code == 200
        assert resp.json()["name"] == "qwen3:8b"

    def test_info_not_found(self, client: TestClient) -> None:
        app = client.app
        app.state.container.manage_ollama.info = AsyncMock(return_value=None)
        resp = client.get("/api/models/nonexistent/info")
        assert resp.status_code == 404
