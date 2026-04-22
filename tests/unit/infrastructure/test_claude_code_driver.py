"""Tests for ClaudeCodeDriver — Claude Code CLI headless mode."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from domain.ports.agent_engine import AgentEngineCapabilities, AgentEngineResult
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.agent_cli._subprocess_base import CLIResult
from infrastructure.agent_cli.claude_code_driver import ClaudeCodeDriver


@pytest.fixture()
def driver():
    return ClaudeCodeDriver(enabled=True, cli_path="claude")


@pytest.fixture()
def disabled_driver():
    return ClaudeCodeDriver(enabled=False)


# ── Construction ──


class TestConstruction:
    def test_engine_type(self, driver):
        assert driver.engine_type == AgentEngineType.CLAUDE_CODE

    def test_default_cli_path(self):
        d = ClaudeCodeDriver(enabled=True)
        assert d._cli_path == "claude"

    def test_custom_cli_path(self):
        d = ClaudeCodeDriver(enabled=True, cli_path="/usr/local/bin/claude")
        assert d._cli_path == "/usr/local/bin/claude"


# ── is_available ──


class TestIsAvailable:
    @pytest.mark.asyncio
    async def test_available_when_enabled_and_binary_exists(self, driver):
        with patch.object(ClaudeCodeDriver, "_check_cli_exists", return_value=True):
            assert await driver.is_available() is True

    @pytest.mark.asyncio
    async def test_unavailable_when_disabled(self, disabled_driver):
        assert await disabled_driver.is_available() is False

    @pytest.mark.asyncio
    async def test_unavailable_when_binary_missing(self, driver):
        with patch.object(ClaudeCodeDriver, "_check_cli_exists", return_value=False):
            assert await driver.is_available() is False


# ── run_task ──


class TestRunTask:
    @pytest.mark.asyncio
    async def test_valid_json_output(self, driver):
        json_output = json.dumps({"result": "Hello world", "session_id": "sess-123"})
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout=json_output, stderr="", returncode=0),
        ):
            result = await driver.run_task("Say hello")
        assert isinstance(result, AgentEngineResult)
        assert result.success is True
        assert result.output == "Hello world"
        assert result.engine == AgentEngineType.CLAUDE_CODE
        assert result.metadata.get("session_id") == "sess-123"

    @pytest.mark.asyncio
    async def test_session_id_in_metadata(self, driver):
        json_output = json.dumps({"result": "ok", "session_id": "abc-456"})
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout=json_output, stderr="", returncode=0),
        ):
            result = await driver.run_task("test")
        assert result.metadata["session_id"] == "abc-456"

    @pytest.mark.asyncio
    async def test_invalid_json_fallback(self, driver):
        """When stdout is not valid JSON, use raw stdout as output."""
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="raw text output", stderr="", returncode=0),
        ):
            result = await driver.run_task("test")
        assert result.success is True
        assert result.output == "raw text output"

    @pytest.mark.asyncio
    async def test_nonzero_exit_code(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="", stderr="error msg", returncode=1),
        ):
            result = await driver.run_task("test")
        assert result.success is False
        assert "error msg" in result.error

    @pytest.mark.asyncio
    async def test_timeout(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="", stderr="Command timed out after 10s", returncode=-1),
        ):
            result = await driver.run_task("test", timeout_seconds=10)
        assert result.success is False
        assert "timed out" in result.error

    @pytest.mark.asyncio
    async def test_disabled_returns_error(self, disabled_driver):
        result = await disabled_driver.run_task("test")
        assert result.success is False
        assert "disabled" in result.error

    @pytest.mark.asyncio
    async def test_command_shape(self, driver):
        """Verify the exact CLI command constructed."""
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ) as mock_run:
            await driver.run_task("Do something")
        cmd = mock_run.call_args[0][0]
        expected = [
            "claude",
            "-p",
            "Do something",
            "--output-format",
            "json",
            "--max-turns",
            "10",
            "--setting-sources",
            "user",
            "--allowedTools",
            "Bash,Read,Write,Edit,WebFetch,WebSearch",
        ]
        assert cmd == expected

    @pytest.mark.asyncio
    async def test_model_override(self, driver):
        """Model flag is appended when specified."""
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ) as mock_run:
            await driver.run_task("test", model="claude-opus-4-6")
        cmd = mock_run.call_args[0][0]
        assert "--model" in cmd
        assert "claude-opus-4-6" in cmd

    @pytest.mark.asyncio
    async def test_no_model_flag_when_none(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ) as mock_run:
            await driver.run_task("test")
        cmd = mock_run.call_args[0][0]
        assert "--model" not in cmd

    @pytest.mark.asyncio
    async def test_duration_measured(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ):
            result = await driver.run_task("test")
        assert result.duration_seconds >= 0.0

    @pytest.mark.asyncio
    async def test_usage_in_metadata(self, driver):
        json_output = json.dumps(
            {
                "result": "ok",
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            }
        )
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout=json_output, stderr="", returncode=0),
        ):
            result = await driver.run_task("test")
        assert result.metadata["usage"] == {"prompt_tokens": 100, "completion_tokens": 50}

    @pytest.mark.asyncio
    async def test_model_from_json_response(self, driver):
        json_output = json.dumps({"result": "ok", "model": "claude-sonnet-4-6"})
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout=json_output, stderr="", returncode=0),
        ):
            result = await driver.run_task("test")
        assert result.model_used == "claude-sonnet-4-6"


# ── get_capabilities ──


class TestGetCapabilities:
    def test_returns_capabilities(self, driver):
        caps = driver.get_capabilities()
        assert isinstance(caps, AgentEngineCapabilities)
        assert caps.engine_type == AgentEngineType.CLAUDE_CODE
        assert caps.max_context_tokens == 200_000
        assert caps.supports_parallel is True
        assert caps.supports_streaming is True
