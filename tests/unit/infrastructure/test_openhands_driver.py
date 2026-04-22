"""Tests for OpenHandsDriver — OpenHands REST API integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domain.ports.agent_engine import AgentEngineCapabilities, AgentEngineResult
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.agent_cli.openhands_driver import OpenHandsDriver


@pytest.fixture()
def driver():
    return OpenHandsDriver(
        base_url="http://localhost:3000",
        model="claude-sonnet-4-6",
        api_key="test-key-123",
    )


@pytest.fixture()
def driver_no_key():
    return OpenHandsDriver(
        base_url="http://localhost:3000",
        model="claude-sonnet-4-6",
    )


# ── Construction ──


class TestConstruction:
    def test_engine_type(self, driver):
        assert driver.engine_type == AgentEngineType.OPENHANDS

    def test_stores_config(self, driver):
        assert driver._base_url == "http://localhost:3000"
        assert driver._model == "claude-sonnet-4-6"
        assert driver._api_key == "test-key-123"

    def test_strips_trailing_slash(self):
        d = OpenHandsDriver(base_url="http://localhost:3000/")
        assert d._base_url == "http://localhost:3000"

    def test_default_api_key_empty(self, driver_no_key):
        assert driver_no_key._api_key == ""


# ── Auth headers ──


class TestHeaders:
    def test_auth_header_with_key(self, driver):
        headers = driver._headers()
        assert headers["Authorization"] == "Bearer test-key-123"

    def test_no_auth_header_without_key(self, driver_no_key):
        headers = driver_no_key._headers()
        assert "Authorization" not in headers

    def test_content_type_always_present(self, driver):
        assert driver._headers()["Content-Type"] == "application/json"


# ── is_available ──


class TestIsAvailable:
    @pytest.mark.asyncio
    async def test_available_when_healthy(self, driver):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch.object(driver, "_request", new_callable=AsyncMock, return_value=mock_resp):
            assert await driver.is_available() is True

    @pytest.mark.asyncio
    async def test_unavailable_on_error(self, driver):
        with patch.object(
            driver, "_request", new_callable=AsyncMock, side_effect=Exception("conn")
        ):
            assert await driver.is_available() is False

    @pytest.mark.asyncio
    async def test_unavailable_on_non_200(self, driver):
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        with patch.object(driver, "_request", new_callable=AsyncMock, return_value=mock_resp):
            assert await driver.is_available() is False


# ── run_task ──


class TestRunTask:
    @pytest.mark.asyncio
    async def test_full_success_flow(self, driver):
        """Settings → create conversation → poll → completed."""
        settings_resp = MagicMock()
        settings_resp.status_code = 200

        create_resp = MagicMock()
        create_resp.status_code = 200
        create_resp.json.return_value = {"conversation_id": "conv-001"}

        poll_resp = MagicMock()
        poll_resp.status_code = 200
        poll_resp.json.return_value = {
            "status": "completed",
            "result": "Task done successfully",
        }

        async def mock_request(method, path, **kwargs):
            if method == "post" and "/settings" in path:
                return settings_resp
            if method == "post":
                return create_resp
            return poll_resp

        with patch.object(driver, "_request", side_effect=mock_request):
            result = await driver.run_task("Fix the bug")

        assert isinstance(result, AgentEngineResult)
        assert result.success is True
        assert result.output == "Task done successfully"
        assert result.engine == AgentEngineType.OPENHANDS
        assert result.metadata["conversation_id"] == "conv-001"

    @pytest.mark.asyncio
    async def test_create_error(self, driver):
        settings_resp = MagicMock()
        settings_resp.status_code = 200
        create_resp = MagicMock()
        create_resp.status_code = 500

        async def mock_request(method, path, **kwargs):
            if method == "post" and "/settings" in path:
                return settings_resp
            return create_resp

        with patch.object(driver, "_request", side_effect=mock_request):
            result = await driver.run_task("test")
        assert result.success is False
        assert "500" in result.error

    @pytest.mark.asyncio
    async def test_create_request_exception(self, driver):
        settings_resp = MagicMock()
        settings_resp.status_code = 200
        call_count = 0

        async def mock_request(method, path, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return settings_resp
            raise Exception("Network error")

        with patch.object(driver, "_request", side_effect=mock_request):
            result = await driver.run_task("test")
        assert result.success is False
        assert "Network error" in result.error

    @pytest.mark.asyncio
    async def test_poll_error_status(self, driver):
        """Poll returns error status."""
        settings_resp = MagicMock()
        settings_resp.status_code = 200
        create_resp = MagicMock()
        create_resp.status_code = 200
        create_resp.json.return_value = {"conversation_id": "conv-002"}

        poll_resp = MagicMock()
        poll_resp.status_code = 200
        poll_resp.json.return_value = {
            "status": "error",
            "error": "Agent crashed",
        }

        async def mock_request(method, path, **kwargs):
            if method == "post" and "/settings" in path:
                return settings_resp
            if method == "post":
                return create_resp
            return poll_resp

        with patch.object(driver, "_request", side_effect=mock_request):
            result = await driver.run_task("test")
        assert result.success is False
        assert "Agent crashed" in result.error
        assert result.metadata["conversation_id"] == "conv-002"

    @pytest.mark.asyncio
    async def test_poll_stopped_status(self, driver):
        settings_resp = MagicMock()
        settings_resp.status_code = 200
        create_resp = MagicMock()
        create_resp.status_code = 200
        create_resp.json.return_value = {"conversation_id": "conv-003"}

        poll_resp = MagicMock()
        poll_resp.status_code = 200
        poll_resp.json.return_value = {"status": "stopped"}

        async def mock_request(method, path, **kwargs):
            if method == "post" and "/settings" in path:
                return settings_resp
            if method == "post":
                return create_resp
            return poll_resp

        with patch.object(driver, "_request", side_effect=mock_request):
            result = await driver.run_task("test")
        # stopped = task completed but agent was stopped (not an error, but not success)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_poll_idle_status_is_success(self, driver):
        """IDLE status from new OpenHands API means task completed."""
        settings_resp = MagicMock()
        settings_resp.status_code = 200
        create_resp = MagicMock()
        create_resp.status_code = 200
        create_resp.json.return_value = {"conversation_id": "conv-idle"}

        poll_resp = MagicMock()
        poll_resp.status_code = 200
        poll_resp.json.return_value = {"status": "IDLE", "result": "4"}

        async def mock_request(method, path, **kwargs):
            if method == "post" and "/settings" in path:
                return settings_resp
            if method == "post":
                return create_resp
            return poll_resp

        with patch.object(driver, "_request", side_effect=mock_request):
            result = await driver.run_task("test")
        assert result.success is True
        assert result.output == "4"

    @pytest.mark.asyncio
    async def test_poll_non_200(self, driver):
        settings_resp = MagicMock()
        settings_resp.status_code = 200
        create_resp = MagicMock()
        create_resp.status_code = 200
        create_resp.json.return_value = {"conversation_id": "conv-004"}

        poll_resp = MagicMock()
        poll_resp.status_code = 500

        async def mock_request(method, path, **kwargs):
            if method == "post" and "/settings" in path:
                return settings_resp
            if method == "post":
                return create_resp
            return poll_resp

        with patch.object(driver, "_request", side_effect=mock_request):
            result = await driver.run_task("test")
        assert result.success is False
        assert "500" in result.error

    @pytest.mark.asyncio
    async def test_poll_timeout(self, driver):
        """Polling exceeds timeout_seconds."""
        settings_resp = MagicMock()
        settings_resp.status_code = 200
        create_resp = MagicMock()
        create_resp.status_code = 200
        create_resp.json.return_value = {"conversation_id": "conv-005"}

        poll_resp = MagicMock()
        poll_resp.status_code = 200
        poll_resp.json.return_value = {"status": "running"}

        async def mock_request(method, path, **kwargs):
            if method == "post" and "/settings" in path:
                return settings_resp
            if method == "post":
                return create_resp
            return poll_resp

        # time.monotonic() is called many times: start, while-check, duration, etc.
        # Provide enough values, then exceed deadline
        times = [0.0, 0.1, 0.2, 0.3, 999.0] + [999.0] * 10

        with (
            patch.object(driver, "_request", side_effect=mock_request),
            patch(
                "infrastructure.agent_cli.openhands_driver.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch("infrastructure.agent_cli.openhands_driver.time.monotonic", side_effect=times),
        ):
            result = await driver.run_task("test", timeout_seconds=5.0)
        assert result.success is False
        assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_model_passing(self, driver):
        """Model is passed via _ensure_settings, not in conversation create body."""
        settings_resp = MagicMock()
        settings_resp.status_code = 200
        create_resp = MagicMock()
        create_resp.status_code = 200
        create_resp.json.return_value = {"conversation_id": "conv-006"}

        poll_resp = MagicMock()
        poll_resp.status_code = 200
        poll_resp.json.return_value = {"status": "completed", "result": "done"}

        settings_calls = []

        async def mock_request(method, path, **kwargs):
            if method == "post" and "/settings" in path:
                settings_calls.append(kwargs.get("json", {}))
                return settings_resp
            if method == "post":
                return create_resp
            return poll_resp

        with patch.object(driver, "_request", side_effect=mock_request):
            result = await driver.run_task("test", model="gpt-4o")
        assert result.success is True
        assert result.model_used == "gpt-4o"
        # Model is sent via settings, not conversation body
        assert len(settings_calls) == 1
        assert settings_calls[0]["llm_model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_default_model(self, driver):
        settings_resp = MagicMock()
        settings_resp.status_code = 200
        create_resp = MagicMock()
        create_resp.status_code = 200
        create_resp.json.return_value = {"conversation_id": "conv-007"}

        poll_resp = MagicMock()
        poll_resp.status_code = 200
        poll_resp.json.return_value = {"status": "completed", "result": "done"}

        settings_calls = []

        async def mock_request(method, path, **kwargs):
            if method == "post" and "/settings" in path:
                settings_calls.append(kwargs.get("json", {}))
                return settings_resp
            if method == "post":
                return create_resp
            return poll_resp

        with patch.object(driver, "_request", side_effect=mock_request):
            result = await driver.run_task("test")
        assert result.model_used == "claude-sonnet-4-6"
        assert settings_calls[0]["llm_model"] == "claude-sonnet-4-6"

    @pytest.mark.asyncio
    async def test_settings_skipped_without_api_key(self, driver_no_key):
        """When no api_key, _ensure_settings is skipped."""
        create_resp = MagicMock()
        create_resp.status_code = 200
        create_resp.json.return_value = {"conversation_id": "conv-nokey"}

        poll_resp = MagicMock()
        poll_resp.status_code = 200
        poll_resp.json.return_value = {"status": "completed", "result": "done"}

        paths_called = []

        async def mock_request(method, path, **kwargs):
            paths_called.append(path)
            if method == "post":
                return create_resp
            return poll_resp

        with patch.object(driver_no_key, "_request", side_effect=mock_request):
            result = await driver_no_key.run_task("test")
        assert result.success is True
        # Settings endpoint should NOT have been called
        assert not any("/settings" in p for p in paths_called)

    @pytest.mark.asyncio
    async def test_ensure_settings_sends_model(self, driver):
        """_ensure_settings sends llm_model and llm_api_key."""
        settings_resp = MagicMock()
        settings_resp.status_code = 200

        captured = {}

        async def mock_request(method, path, **kwargs):
            if "/settings" in path:
                captured.update(kwargs.get("json", {}))
                return settings_resp
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"conversation_id": "x"}
            return resp

        with patch.object(driver, "_request", side_effect=mock_request):
            ok = await driver._ensure_settings("test-model")
        assert ok is True
        assert captured["llm_model"] == "test-model"
        assert captured["llm_api_key"] == "test-key-123"
        assert captured["agent"] == "CodeActAgent"

    @pytest.mark.asyncio
    async def test_conversation_id_in_metadata(self, driver):
        settings_resp = MagicMock()
        settings_resp.status_code = 200
        create_resp = MagicMock()
        create_resp.status_code = 200
        create_resp.json.return_value = {"conversation_id": "conv-meta"}

        poll_resp = MagicMock()
        poll_resp.status_code = 200
        poll_resp.json.return_value = {"status": "completed", "result": "done"}

        async def mock_request(method, path, **kwargs):
            if method == "post" and "/settings" in path:
                return settings_resp
            if method == "post":
                return create_resp
            return poll_resp

        with patch.object(driver, "_request", side_effect=mock_request):
            result = await driver.run_task("test")
        assert result.metadata["conversation_id"] == "conv-meta"

    @pytest.mark.asyncio
    async def test_duration_measured(self, driver):
        settings_resp = MagicMock()
        settings_resp.status_code = 200
        create_resp = MagicMock()
        create_resp.status_code = 200
        create_resp.json.return_value = {"conversation_id": "conv-dur"}

        poll_resp = MagicMock()
        poll_resp.status_code = 200
        poll_resp.json.return_value = {"status": "completed", "result": "done"}

        async def mock_request(method, path, **kwargs):
            if method == "post" and "/settings" in path:
                return settings_resp
            if method == "post":
                return create_resp
            return poll_resp

        with patch.object(driver, "_request", side_effect=mock_request):
            result = await driver.run_task("test")
        assert result.duration_seconds >= 0.0


# ── get_capabilities ──


class TestGetCapabilities:
    def test_returns_capabilities(self, driver):
        caps = driver.get_capabilities()
        assert isinstance(caps, AgentEngineCapabilities)
        assert caps.engine_type == AgentEngineType.OPENHANDS
        assert caps.supports_sandbox is True
        assert caps.supports_parallel is True
        assert caps.supports_streaming is True
