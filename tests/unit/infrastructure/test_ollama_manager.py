"""Tests for OllamaManager — Ollama lifecycle management."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from infrastructure.llm.ollama_manager import OllamaManager


@pytest.fixture
def manager():
    return OllamaManager(base_url="http://test:11434")


def _ok_response(json_data: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = json_data or {}
    return resp


def _error_response(status_code: int = 500) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    return resp


class TestIsRunning:
    async def test_returns_true_when_healthy(self, manager: OllamaManager) -> None:
        manager._request = AsyncMock(return_value=_ok_response())
        assert await manager.is_running() is True

    async def test_returns_false_on_connection_error(self, manager: OllamaManager) -> None:
        manager._request = AsyncMock(side_effect=httpx.ConnectError("refused"))
        assert await manager.is_running() is False

    async def test_returns_false_on_timeout(self, manager: OllamaManager) -> None:
        manager._request = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        assert await manager.is_running() is False


class TestListModels:
    async def test_returns_model_names(self, manager: OllamaManager) -> None:
        data = {"models": [{"name": "qwen3:8b"}, {"name": "llama3.2:3b"}]}
        manager._request = AsyncMock(return_value=_ok_response(data))
        result = await manager.list_models()
        assert result == ["qwen3:8b", "llama3.2:3b"]

    async def test_returns_empty_on_connection_error(self, manager: OllamaManager) -> None:
        manager._request = AsyncMock(side_effect=httpx.ConnectError("down"))
        assert await manager.list_models() == []

    async def test_returns_empty_on_bad_status(self, manager: OllamaManager) -> None:
        manager._request = AsyncMock(return_value=_error_response(500))
        assert await manager.list_models() == []


class TestEnsureModel:
    async def test_already_installed(self, manager: OllamaManager) -> None:
        data = {"models": [{"name": "qwen3:8b"}]}
        manager._request = AsyncMock(return_value=_ok_response(data))
        assert await manager.ensure_model("qwen3:8b") is True

    async def test_pulls_when_missing(self, manager: OllamaManager) -> None:
        list_resp = _ok_response({"models": []})
        pull_resp = _ok_response()
        manager._request = AsyncMock(side_effect=[list_resp, pull_resp])
        assert await manager.ensure_model("qwen3:8b") is True

    async def test_returns_false_on_pull_failure(self, manager: OllamaManager) -> None:
        list_resp = _ok_response({"models": []})
        manager._request = AsyncMock(side_effect=[list_resp, httpx.ConnectError("fail")])
        assert await manager.ensure_model("qwen3:8b") is False


class TestRecommendModel:
    def test_4gb(self) -> None:
        assert OllamaManager.get_recommended_model(4) == "llama3.2:3b"

    def test_8gb(self) -> None:
        assert OllamaManager.get_recommended_model(8) == "qwen3:8b"

    def test_16gb(self) -> None:
        assert OllamaManager.get_recommended_model(16) == "qwen3:8b"

    def test_32gb(self) -> None:
        assert OllamaManager.get_recommended_model(32) == "qwen3-coder:30b"

    def test_64gb(self) -> None:
        assert OllamaManager.get_recommended_model(64) == "qwen3-coder:30b"
