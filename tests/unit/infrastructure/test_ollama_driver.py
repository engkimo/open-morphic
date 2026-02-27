"""Tests for OllamaEngineDriver — wraps LiteLLMGateway + OllamaManager."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from domain.ports.agent_engine import AgentEngineCapabilities, AgentEngineResult
from domain.ports.llm_gateway import LLMResponse
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.agent_cli.ollama_driver import OllamaEngineDriver


@pytest.fixture()
def mock_gateway():
    gw = AsyncMock()
    return gw


@pytest.fixture()
def mock_ollama():
    om = AsyncMock()
    om.is_running = AsyncMock(return_value=True)
    return om


@pytest.fixture()
def driver(mock_gateway, mock_ollama):
    return OllamaEngineDriver(gateway=mock_gateway, ollama=mock_ollama)


# ── Construction ──


class TestConstruction:
    def test_engine_type(self, driver):
        assert driver.engine_type == AgentEngineType.OLLAMA

    def test_stores_dependencies(self, driver, mock_gateway, mock_ollama):
        assert driver._gateway is mock_gateway
        assert driver._ollama is mock_ollama


# ── is_available ──


class TestIsAvailable:
    @pytest.mark.asyncio()
    async def test_available_when_running(self, driver, mock_ollama):
        mock_ollama.is_running.return_value = True
        assert await driver.is_available() is True

    @pytest.mark.asyncio()
    async def test_unavailable_when_down(self, driver, mock_ollama):
        mock_ollama.is_running.return_value = False
        assert await driver.is_available() is False


# ── run_task ──


class TestRunTask:
    @pytest.mark.asyncio()
    async def test_success(self, driver, mock_gateway):
        mock_gateway.complete.return_value = LLMResponse(
            content="Hello world",
            model="ollama/qwen3:8b",
            prompt_tokens=10,
            completion_tokens=20,
            cost_usd=0.0,
        )
        result = await driver.run_task("Say hello")
        assert isinstance(result, AgentEngineResult)
        assert result.success is True
        assert result.output == "Hello world"
        assert result.engine == AgentEngineType.OLLAMA
        assert result.cost_usd == 0.0

    @pytest.mark.asyncio()
    async def test_auto_prefix_ollama_model(self, driver, mock_gateway):
        """Model names without 'ollama/' prefix get auto-prefixed."""
        mock_gateway.complete.return_value = LLMResponse(
            content="ok",
            model="ollama/qwen3:8b",
            prompt_tokens=5,
            completion_tokens=5,
            cost_usd=0.0,
        )
        await driver.run_task("test", model="qwen3:8b")
        call_kwargs = mock_gateway.complete.call_args
        assert call_kwargs[1]["model"] == "ollama/qwen3:8b"

    @pytest.mark.asyncio()
    async def test_preserves_ollama_prefix(self, driver, mock_gateway):
        """Model names already prefixed are not double-prefixed."""
        mock_gateway.complete.return_value = LLMResponse(
            content="ok",
            model="ollama/qwen3:8b",
            prompt_tokens=5,
            completion_tokens=5,
            cost_usd=0.0,
        )
        await driver.run_task("test", model="ollama/qwen3:8b")
        call_kwargs = mock_gateway.complete.call_args
        assert call_kwargs[1]["model"] == "ollama/qwen3:8b"

    @pytest.mark.asyncio()
    async def test_failure_returns_error_result(self, driver, mock_gateway):
        mock_gateway.complete.side_effect = Exception("Connection refused")
        result = await driver.run_task("test")
        assert result.success is False
        assert "Connection refused" in result.error
        assert result.engine == AgentEngineType.OLLAMA

    @pytest.mark.asyncio()
    async def test_cost_from_response(self, driver, mock_gateway):
        mock_gateway.complete.return_value = LLMResponse(
            content="result",
            model="ollama/qwen3:8b",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.0,
        )
        result = await driver.run_task("test")
        assert result.cost_usd == 0.0

    @pytest.mark.asyncio()
    async def test_duration_measured(self, driver, mock_gateway):
        mock_gateway.complete.return_value = LLMResponse(
            content="result",
            model="ollama/qwen3:8b",
            prompt_tokens=10,
            completion_tokens=10,
            cost_usd=0.0,
        )
        result = await driver.run_task("test")
        assert result.duration_seconds >= 0.0

    @pytest.mark.asyncio()
    async def test_model_used_in_result(self, driver, mock_gateway):
        mock_gateway.complete.return_value = LLMResponse(
            content="ok",
            model="ollama/deepseek-r1:8b",
            prompt_tokens=5,
            completion_tokens=5,
            cost_usd=0.0,
        )
        result = await driver.run_task("test", model="deepseek-r1:8b")
        assert result.model_used == "ollama/deepseek-r1:8b"

    @pytest.mark.asyncio()
    async def test_default_model_used(self, driver, mock_gateway):
        """When no model specified, uses default ollama model."""
        mock_gateway.complete.return_value = LLMResponse(
            content="ok",
            model="ollama/qwen3:8b",
            prompt_tokens=5,
            completion_tokens=5,
            cost_usd=0.0,
        )
        await driver.run_task("test")
        call_kwargs = mock_gateway.complete.call_args
        assert "model" in call_kwargs[1]


# ── get_capabilities ──


class TestGetCapabilities:
    def test_returns_capabilities(self, driver):
        caps = driver.get_capabilities()
        assert isinstance(caps, AgentEngineCapabilities)
        assert caps.engine_type == AgentEngineType.OLLAMA
        assert caps.cost_per_hour_usd == 0.0
        assert caps.supports_sandbox is False
