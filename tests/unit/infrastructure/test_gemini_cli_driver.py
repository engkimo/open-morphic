"""Tests for GeminiCLIDriver — Gemini CLI with 2M token context."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from domain.ports.agent_engine import AgentEngineCapabilities, AgentEngineResult
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.agent_cli._subprocess_base import CLIResult
from infrastructure.agent_cli.gemini_cli_driver import GeminiCLIDriver


@pytest.fixture()
def driver():
    return GeminiCLIDriver(enabled=True, cli_path="gemini", api_key="test-key")


@pytest.fixture()
def disabled_driver():
    return GeminiCLIDriver(enabled=False)


# ── Construction ──


class TestConstruction:
    def test_engine_type(self, driver):
        assert driver.engine_type == AgentEngineType.GEMINI_CLI

    def test_default_cli_path(self):
        d = GeminiCLIDriver(enabled=True)
        assert d._cli_path == "gemini"

    def test_custom_cli_path(self):
        d = GeminiCLIDriver(enabled=True, cli_path="/usr/local/bin/gemini")
        assert d._cli_path == "/usr/local/bin/gemini"

    def test_api_key_stored(self):
        d = GeminiCLIDriver(enabled=True, api_key="my-key")
        assert d._api_key == "my-key"


# ── is_available ──


class TestIsAvailable:
    @pytest.mark.asyncio
    async def test_available_when_enabled_and_binary_and_key(self, driver):
        with patch.object(GeminiCLIDriver, "_check_cli_exists", return_value=True):
            assert await driver.is_available() is True

    @pytest.mark.asyncio
    async def test_unavailable_when_disabled(self, disabled_driver):
        assert await disabled_driver.is_available() is False

    @pytest.mark.asyncio
    async def test_unavailable_when_binary_missing(self, driver):
        with patch.object(GeminiCLIDriver, "_check_cli_exists", return_value=False):
            assert await driver.is_available() is False

    @pytest.mark.asyncio
    async def test_unavailable_when_no_api_key(self):
        d = GeminiCLIDriver(enabled=True, cli_path="gemini")
        with (
            patch.object(GeminiCLIDriver, "_check_cli_exists", return_value=True),
            patch.dict("os.environ", {}, clear=True),
        ):
            assert await d.is_available() is False

    @pytest.mark.asyncio
    async def test_available_with_google_gemini_api_key_env(self):
        d = GeminiCLIDriver(enabled=True, cli_path="gemini")
        with (
            patch.object(GeminiCLIDriver, "_check_cli_exists", return_value=True),
            patch.dict("os.environ", {"GOOGLE_GEMINI_API_KEY": "k"}, clear=True),
        ):
            assert await d.is_available() is True

    @pytest.mark.asyncio
    async def test_available_with_gemini_api_key_env(self):
        d = GeminiCLIDriver(enabled=True, cli_path="gemini")
        with (
            patch.object(GeminiCLIDriver, "_check_cli_exists", return_value=True),
            patch.dict("os.environ", {"GEMINI_API_KEY": "k"}, clear=True),
        ):
            assert await d.is_available() is True


# ── run_task ──


class TestRunTask:
    @pytest.mark.asyncio
    async def test_valid_json_output(self, driver):
        json_output = json.dumps({"result": "Analysis complete"})
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout=json_output, stderr="", returncode=0),
        ):
            result = await driver.run_task("Analyze document")
        assert isinstance(result, AgentEngineResult)
        assert result.success is True
        assert result.output == "Analysis complete"
        assert result.engine == AgentEngineType.GEMINI_CLI

    @pytest.mark.asyncio
    async def test_invalid_json_fallback(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="raw gemini output", stderr="", returncode=0),
        ):
            result = await driver.run_task("test")
        assert result.success is True
        assert result.output == "raw gemini output"

    @pytest.mark.asyncio
    async def test_nonzero_exit_code(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="", stderr="gemini error", returncode=1),
        ):
            result = await driver.run_task("test")
        assert result.success is False
        assert "gemini error" in result.error

    @pytest.mark.asyncio
    async def test_timeout(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="", stderr="Command timed out after 300s", returncode=-1),
        ):
            result = await driver.run_task("test")
        assert result.success is False
        assert "timed out" in result.error

    @pytest.mark.asyncio
    async def test_disabled_returns_error(self, disabled_driver):
        result = await disabled_driver.run_task("test")
        assert result.success is False
        assert "disabled" in result.error

    @pytest.mark.asyncio
    async def test_command_shape(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ) as mock_run:
            await driver.run_task("Analyze this")
        cmd = mock_run.call_args[0][0]
        assert cmd == ["gemini", "-p", "Analyze this", "--output-format", "json"]

    @pytest.mark.asyncio
    async def test_env_passes_gemini_api_key(self, driver):
        """Subprocess env includes GEMINI_API_KEY."""
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ) as mock_run:
            await driver.run_task("test")
        env = mock_run.call_args[1].get("env") or mock_run.call_args.kwargs.get("env")
        assert env is not None
        assert env["GEMINI_API_KEY"] == "test-key"

    @pytest.mark.asyncio
    async def test_model_override_uses_m_flag(self, driver):
        """Gemini uses -m for model selection (not --model)."""
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ) as mock_run:
            await driver.run_task("test", model="gemini-2.5-pro")
        cmd = mock_run.call_args[0][0]
        assert "-m" in cmd
        assert "gemini-2.5-pro" in cmd

    @pytest.mark.asyncio
    async def test_no_model_flag_when_none(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ) as mock_run:
            await driver.run_task("test")
        cmd = mock_run.call_args[0][0]
        assert "-m" not in cmd

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
                "usage": {"prompt_tokens": 500, "completion_tokens": 200},
            }
        )
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout=json_output, stderr="", returncode=0),
        ):
            result = await driver.run_task("test")
        assert result.metadata["usage"]["prompt_tokens"] == 500

    @pytest.mark.asyncio
    async def test_model_from_json_response(self, driver):
        json_output = json.dumps({"result": "ok", "model": "gemini-2.5-flash"})
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout=json_output, stderr="", returncode=0),
        ):
            result = await driver.run_task("test")
        assert result.model_used == "gemini-2.5-flash"

    @pytest.mark.asyncio
    async def test_empty_stderr_uses_exit_code(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="", stderr="", returncode=3),
        ):
            result = await driver.run_task("test")
        assert result.success is False
        assert "Exit code 3" in result.error

    @pytest.mark.asyncio
    async def test_litellm_prefix_stripped_from_model(self, driver):
        """LiteLLM-style 'gemini/model-name' is stripped to 'model-name' for CLI."""
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ) as mock_run:
            await driver.run_task("test", model="gemini/gemini-3-pro-preview")
        cmd = mock_run.call_args[0][0]
        assert "-m" in cmd
        assert "gemini-3-pro-preview" in cmd
        assert "gemini/gemini-3-pro-preview" not in cmd

    @pytest.mark.asyncio
    async def test_model_without_prefix_unchanged(self, driver):
        """Model names without provider prefix are passed through unchanged."""
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ) as mock_run:
            await driver.run_task("test", model="gemini-2.5-flash")
        cmd = mock_run.call_args[0][0]
        assert "gemini-2.5-flash" in cmd

    @pytest.mark.asyncio
    async def test_response_key_parsed(self, driver):
        """Gemini CLI uses 'response' key (not 'result')."""
        json_output = json.dumps({"response": "The answer is 4."})
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout=json_output, stderr="", returncode=0),
        ):
            result = await driver.run_task("test")
        assert result.output == "The answer is 4."

    @pytest.mark.asyncio
    async def test_stats_models_parsed(self, driver):
        """Token usage extracted from stats.models for cost tracking."""
        json_output = json.dumps(
            {
                "response": "4",
                "stats": {
                    "models": {
                        "gemini-2.5-flash-lite": {
                            "tokens": {"input": 3000, "candidates": 50},
                            "roles": {"utility_router": {}},
                        },
                        "gemini-3-pro-preview": {
                            "tokens": {"input": 800, "candidates": 100},
                            "roles": {"main": {}},
                        },
                    },
                },
            }
        )
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout=json_output, stderr="", returncode=0),
        ):
            result = await driver.run_task("test")
        assert result.output == "4"
        assert result.metadata["usage"]["input_tokens"] == 3800
        assert result.metadata["usage"]["output_tokens"] == 150
        assert result.model_used == "gemini-3-pro-preview"


# ── get_capabilities ──


class TestGetCapabilities:
    def test_returns_capabilities(self, driver):
        caps = driver.get_capabilities()
        assert isinstance(caps, AgentEngineCapabilities)
        assert caps.engine_type == AgentEngineType.GEMINI_CLI
        assert caps.max_context_tokens == 2_000_000
        assert caps.cost_per_hour_usd == 0.0
        assert caps.supports_streaming is True
