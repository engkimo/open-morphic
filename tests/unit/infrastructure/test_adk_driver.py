"""Tests for ADKDriver — Google ADK (Agent Development Kit) engine driver."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domain.ports.agent_engine import AgentEngineCapabilities, AgentEngineResult
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.agent_cli.adk_driver import ADKDriver

# ── Construction ──


class TestConstruction:
    def test_engine_type(self):
        driver = ADKDriver()
        assert driver.engine_type == AgentEngineType.ADK

    def test_default_model(self):
        driver = ADKDriver()
        assert driver._model == "gemini-2.5-flash"

    def test_custom_model(self):
        driver = ADKDriver(model="gemini-2.5-pro")
        assert driver._model == "gemini-2.5-pro"

    def test_enabled_flag(self):
        driver = ADKDriver(enabled=False)
        assert driver._enabled is False


# ── is_available ──


class TestIsAvailable:
    @pytest.mark.asyncio()
    async def test_available_when_enabled_and_installed(self):
        driver = ADKDriver(enabled=True)
        with patch("infrastructure.agent_cli.adk_driver._ADK_AVAILABLE", True):
            assert await driver.is_available() is True

    @pytest.mark.asyncio()
    async def test_unavailable_when_disabled(self):
        driver = ADKDriver(enabled=False)
        with patch("infrastructure.agent_cli.adk_driver._ADK_AVAILABLE", True):
            assert await driver.is_available() is False

    @pytest.mark.asyncio()
    async def test_unavailable_when_not_installed(self):
        driver = ADKDriver(enabled=True)
        with patch("infrastructure.agent_cli.adk_driver._ADK_AVAILABLE", False):
            assert await driver.is_available() is False


# ── run_task ──


class TestRunTask:
    @pytest.mark.asyncio()
    async def test_success(self):
        driver = ADKDriver(enabled=True)

        # Mock the ADK classes
        mock_event = MagicMock()
        mock_event.is_final_response.return_value = True
        mock_part = MagicMock()
        mock_part.text = "Hello from ADK"
        mock_event.content = MagicMock()
        mock_event.content.parts = [mock_part]

        async def mock_run_async(**kwargs):
            yield mock_event

        mock_session = MagicMock()
        mock_session.id = "test-session-id"

        mock_session_service = MagicMock()
        mock_session_service.create_session = AsyncMock(return_value=mock_session)

        mock_runner = MagicMock()
        mock_runner.run_async = mock_run_async

        with (
            patch("infrastructure.agent_cli.adk_driver._ADK_AVAILABLE", True),
            patch("infrastructure.agent_cli.adk_driver.LlmAgent"),
            patch("infrastructure.agent_cli.adk_driver.Runner", return_value=mock_runner),
            patch(
                "infrastructure.agent_cli.adk_driver.InMemorySessionService",
                return_value=mock_session_service,
            ),
            patch("infrastructure.agent_cli.adk_driver.Content"),
            patch("infrastructure.agent_cli.adk_driver.Part"),
        ):
            result = await driver.run_task("Say hello")

        assert isinstance(result, AgentEngineResult)
        assert result.success is True
        assert result.output == "Hello from ADK"
        assert result.engine == AgentEngineType.ADK
        assert result.cost_usd == 0.0
        assert result.duration_seconds >= 0.0

    @pytest.mark.asyncio()
    async def test_model_override(self):
        driver = ADKDriver(enabled=True, model="gemini-2.5-flash")

        mock_event = MagicMock()
        mock_event.is_final_response.return_value = True
        mock_part = MagicMock()
        mock_part.text = "ok"
        mock_event.content = MagicMock()
        mock_event.content.parts = [mock_part]

        async def mock_run_async(**kwargs):
            yield mock_event

        mock_session = MagicMock()
        mock_session.id = "s1"
        mock_session_service = MagicMock()
        mock_session_service.create_session = AsyncMock(return_value=mock_session)
        mock_runner = MagicMock()
        mock_runner.run_async = mock_run_async
        mock_agent_cls = MagicMock()

        with (
            patch("infrastructure.agent_cli.adk_driver._ADK_AVAILABLE", True),
            patch("infrastructure.agent_cli.adk_driver.LlmAgent", mock_agent_cls),
            patch("infrastructure.agent_cli.adk_driver.Runner", return_value=mock_runner),
            patch(
                "infrastructure.agent_cli.adk_driver.InMemorySessionService",
                return_value=mock_session_service,
            ),
            patch("infrastructure.agent_cli.adk_driver.Content"),
            patch("infrastructure.agent_cli.adk_driver.Part"),
        ):
            result = await driver.run_task("test", model="gemini-2.5-pro")

        assert result.success is True
        assert result.model_used == "gemini-2.5-pro"
        # Verify LlmAgent was called with overridden model
        mock_agent_cls.assert_called_once()
        call_kwargs = mock_agent_cls.call_args
        assert call_kwargs[1]["model"] == "gemini-2.5-pro"

    @pytest.mark.asyncio()
    async def test_failure_returns_error_result(self):
        driver = ADKDriver(enabled=True)

        with (
            patch("infrastructure.agent_cli.adk_driver._ADK_AVAILABLE", True),
            patch(
                "infrastructure.agent_cli.adk_driver.LlmAgent",
                side_effect=RuntimeError("API error"),
            ),
        ):
            result = await driver.run_task("test")

        assert result.success is False
        assert "API error" in result.error
        assert result.engine == AgentEngineType.ADK
        assert result.duration_seconds >= 0.0

    @pytest.mark.asyncio()
    async def test_disabled_returns_error(self):
        driver = ADKDriver(enabled=False)
        result = await driver.run_task("test")
        assert result.success is False
        assert "disabled" in result.error.lower()

    @pytest.mark.asyncio()
    async def test_not_installed_returns_error(self):
        driver = ADKDriver(enabled=True)
        with patch("infrastructure.agent_cli.adk_driver._ADK_AVAILABLE", False):
            result = await driver.run_task("test")
        assert result.success is False
        assert "not installed" in result.error.lower()

    @pytest.mark.asyncio()
    async def test_duration_measured(self):
        driver = ADKDriver(enabled=True)

        mock_event = MagicMock()
        mock_event.is_final_response.return_value = True
        mock_part = MagicMock()
        mock_part.text = "result"
        mock_event.content = MagicMock()
        mock_event.content.parts = [mock_part]

        async def mock_run_async(**kwargs):
            yield mock_event

        mock_session = MagicMock()
        mock_session.id = "s1"
        mock_session_service = MagicMock()
        mock_session_service.create_session = AsyncMock(return_value=mock_session)
        mock_runner = MagicMock()
        mock_runner.run_async = mock_run_async

        with (
            patch("infrastructure.agent_cli.adk_driver._ADK_AVAILABLE", True),
            patch("infrastructure.agent_cli.adk_driver.LlmAgent"),
            patch("infrastructure.agent_cli.adk_driver.Runner", return_value=mock_runner),
            patch(
                "infrastructure.agent_cli.adk_driver.InMemorySessionService",
                return_value=mock_session_service,
            ),
            patch("infrastructure.agent_cli.adk_driver.Content"),
            patch("infrastructure.agent_cli.adk_driver.Part"),
        ):
            result = await driver.run_task("test")

        assert result.duration_seconds >= 0.0


# ── get_capabilities ──


class TestGetCapabilities:
    def test_returns_capabilities(self):
        driver = ADKDriver()
        caps = driver.get_capabilities()
        assert isinstance(caps, AgentEngineCapabilities)
        assert caps.engine_type == AgentEngineType.ADK

    def test_parallel_support(self):
        driver = ADKDriver()
        caps = driver.get_capabilities()
        assert caps.supports_parallel is True

    def test_cost_free(self):
        driver = ADKDriver()
        caps = driver.get_capabilities()
        assert caps.cost_per_hour_usd == 0.0

    def test_2m_context(self):
        driver = ADKDriver()
        caps = driver.get_capabilities()
        assert caps.max_context_tokens == 2_000_000
