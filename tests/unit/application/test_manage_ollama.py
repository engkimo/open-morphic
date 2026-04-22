"""Tests for ManageOllamaUseCase."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from application.use_cases.manage_ollama import ManageOllamaUseCase


@pytest.fixture
def ollama() -> AsyncMock:
    mock = AsyncMock()
    mock.is_running.return_value = True
    mock.list_models.return_value = ["qwen3:8b", "deepseek-r1:8b"]
    mock.get_running_models.return_value = [{"name": "qwen3:8b"}]
    return mock


@pytest.fixture
def settings() -> MagicMock:
    s = MagicMock()
    s.ollama_default_model = "qwen3:8b"
    return s


@pytest.fixture
def use_case(ollama: AsyncMock, settings: MagicMock) -> ManageOllamaUseCase:
    return ManageOllamaUseCase(ollama=ollama, settings=settings)


class TestManageOllamaUseCase:
    async def test_status(self, use_case: ManageOllamaUseCase) -> None:
        result = await use_case.status()
        assert result.running is True
        assert len(result.models) == 2
        assert result.default_model == "qwen3:8b"

    async def test_status_when_not_running(
        self, use_case: ManageOllamaUseCase, ollama: AsyncMock
    ) -> None:
        ollama.is_running.return_value = False
        result = await use_case.status()
        assert result.running is False
        assert result.models == []

    async def test_pull(self, use_case: ManageOllamaUseCase, ollama: AsyncMock) -> None:
        ollama.pull_model.return_value = True
        result = await use_case.pull("phi4:14b")
        assert result is True
        ollama.pull_model.assert_awaited_once_with("phi4:14b")

    async def test_delete(self, use_case: ManageOllamaUseCase, ollama: AsyncMock) -> None:
        ollama.delete_model.return_value = True
        result = await use_case.delete("deepseek-r1:8b")
        assert result is True
        ollama.delete_model.assert_awaited_once_with("deepseek-r1:8b")

    async def test_info(self, use_case: ManageOllamaUseCase, ollama: AsyncMock) -> None:
        ollama.model_info.return_value = {"modelfile": "...", "parameters": "7B"}
        result = await use_case.info("qwen3:8b")
        assert result["parameters"] == "7B"

    async def test_switch_default_existing(
        self, use_case: ManageOllamaUseCase, ollama: AsyncMock, settings: MagicMock
    ) -> None:
        result = await use_case.switch_default("deepseek-r1:8b")
        assert result is True
        assert settings.ollama_default_model == "deepseek-r1:8b"

    async def test_switch_default_pulls_if_missing(
        self, use_case: ManageOllamaUseCase, ollama: AsyncMock, settings: MagicMock
    ) -> None:
        ollama.list_models.return_value = ["qwen3:8b"]
        ollama.pull_model.return_value = True
        result = await use_case.switch_default("phi4:14b")
        assert result is True
        ollama.pull_model.assert_awaited_once_with("phi4:14b")
        assert settings.ollama_default_model == "phi4:14b"

    async def test_switch_default_fails_if_pull_fails(
        self, use_case: ManageOllamaUseCase, ollama: AsyncMock, settings: MagicMock
    ) -> None:
        ollama.list_models.return_value = ["qwen3:8b"]
        ollama.pull_model.return_value = False
        result = await use_case.switch_default("nonexistent:99b")
        assert result is False
        assert settings.ollama_default_model == "qwen3:8b"  # unchanged

    async def test_delete_failure(self, use_case: ManageOllamaUseCase, ollama: AsyncMock) -> None:
        ollama.delete_model.return_value = False
        result = await use_case.delete("x")
        assert result is False
