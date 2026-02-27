"""Tests for CodexCLIDriver — OpenAI Codex CLI exec mode."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from domain.ports.agent_engine import AgentEngineCapabilities, AgentEngineResult
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.agent_cli._subprocess_base import CLIResult
from infrastructure.agent_cli.codex_cli_driver import CodexCLIDriver


@pytest.fixture()
def driver():
    return CodexCLIDriver(enabled=True, cli_path="codex")


@pytest.fixture()
def disabled_driver():
    return CodexCLIDriver(enabled=False)


# ── Construction ──


class TestConstruction:
    def test_engine_type(self, driver):
        assert driver.engine_type == AgentEngineType.CODEX_CLI

    def test_default_cli_path(self):
        d = CodexCLIDriver(enabled=True)
        assert d._cli_path == "codex"

    def test_custom_cli_path(self):
        d = CodexCLIDriver(enabled=True, cli_path="/opt/codex")
        assert d._cli_path == "/opt/codex"


# ── is_available ──


class TestIsAvailable:
    @pytest.mark.asyncio()
    async def test_available_when_enabled_and_binary_exists(self, driver):
        with patch.object(CodexCLIDriver, "_check_cli_exists", return_value=True):
            assert await driver.is_available() is True

    @pytest.mark.asyncio()
    async def test_unavailable_when_disabled(self, disabled_driver):
        assert await disabled_driver.is_available() is False

    @pytest.mark.asyncio()
    async def test_unavailable_when_binary_missing(self, driver):
        with patch.object(CodexCLIDriver, "_check_cli_exists", return_value=False):
            assert await driver.is_available() is False


# ── run_task ──


class TestRunTask:
    @pytest.mark.asyncio()
    async def test_valid_json_output(self, driver):
        json_output = json.dumps({"result": "Generated code"})
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout=json_output, stderr="", returncode=0),
        ):
            result = await driver.run_task("Write a function")
        assert isinstance(result, AgentEngineResult)
        assert result.success is True
        assert result.output == "Generated code"
        assert result.engine == AgentEngineType.CODEX_CLI

    @pytest.mark.asyncio()
    async def test_invalid_json_fallback(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="plain text", stderr="", returncode=0),
        ):
            result = await driver.run_task("test")
        assert result.success is True
        assert result.output == "plain text"

    @pytest.mark.asyncio()
    async def test_nonzero_exit_code(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="", stderr="codex error", returncode=1),
        ):
            result = await driver.run_task("test")
        assert result.success is False
        assert "codex error" in result.error

    @pytest.mark.asyncio()
    async def test_timeout(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="", stderr="Command timed out after 60s", returncode=-1),
        ):
            result = await driver.run_task("test", timeout_seconds=60)
        assert result.success is False
        assert "timed out" in result.error

    @pytest.mark.asyncio()
    async def test_disabled_returns_error(self, disabled_driver):
        result = await disabled_driver.run_task("test")
        assert result.success is False
        assert "disabled" in result.error

    @pytest.mark.asyncio()
    async def test_command_shape(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ) as mock_run:
            await driver.run_task("Build feature")
        cmd = mock_run.call_args[0][0]
        assert cmd == ["codex", "exec", "--json", "--full-auto", "Build feature"]

    @pytest.mark.asyncio()
    async def test_model_override(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ) as mock_run:
            await driver.run_task("test", model="gpt-5-codex")
        cmd = mock_run.call_args[0][0]
        assert "--model" in cmd
        assert "gpt-5-codex" in cmd

    @pytest.mark.asyncio()
    async def test_no_model_flag_when_none(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ) as mock_run:
            await driver.run_task("test")
        cmd = mock_run.call_args[0][0]
        assert "--model" not in cmd

    @pytest.mark.asyncio()
    async def test_duration_measured(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ):
            result = await driver.run_task("test")
        assert result.duration_seconds >= 0.0

    @pytest.mark.asyncio()
    async def test_usage_in_metadata(self, driver):
        json_output = json.dumps(
            {
                "result": "ok",
                "usage": {"prompt_tokens": 200, "completion_tokens": 100},
            }
        )
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout=json_output, stderr="", returncode=0),
        ):
            result = await driver.run_task("test")
        assert result.metadata["usage"]["prompt_tokens"] == 200

    @pytest.mark.asyncio()
    async def test_model_from_json_response(self, driver):
        json_output = json.dumps({"result": "ok", "model": "gpt-5-codex"})
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout=json_output, stderr="", returncode=0),
        ):
            result = await driver.run_task("test")
        assert result.model_used == "gpt-5-codex"

    @pytest.mark.asyncio()
    async def test_empty_stderr_uses_exit_code(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="", stderr="", returncode=2),
        ):
            result = await driver.run_task("test")
        assert result.success is False
        assert "Exit code 2" in result.error


# ── get_capabilities ──


class TestGetCapabilities:
    def test_returns_capabilities(self, driver):
        caps = driver.get_capabilities()
        assert isinstance(caps, AgentEngineCapabilities)
        assert caps.engine_type == AgentEngineType.CODEX_CLI
        assert caps.supports_sandbox is True
        assert caps.supports_mcp is True
