"""Tests for engine cost tracking integration in CLI drivers."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from infrastructure.agent_cli._subprocess_base import CLIResult
from infrastructure.agent_cli.claude_code_driver import ClaudeCodeDriver
from infrastructure.agent_cli.codex_cli_driver import CodexCLIDriver
from infrastructure.agent_cli.gemini_cli_driver import GeminiCLIDriver


def _make_cli_result(data: dict, returncode: int = 0) -> CLIResult:
    return CLIResult(
        returncode=returncode,
        stdout=json.dumps(data),
        stderr="",
    )


class TestClaudeCodeDriverCost:
    @pytest.mark.asyncio
    async def test_cost_from_usage_metadata(self):
        driver = ClaudeCodeDriver(enabled=True)
        data = {
            "result": "Hello",
            "model": "claude-sonnet-4-6",
            "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
        }
        with patch.object(driver, "_run_cli", new_callable=AsyncMock) as mock_cli:
            mock_cli.return_value = _make_cli_result(data)
            result = await driver.run_task("test")

        assert result.success
        assert result.cost_usd > 0.0
        expected = (1000 / 1_000_000) * 3.0 + (500 / 1_000_000) * 15.0
        assert result.cost_usd == round(expected, 6)

    @pytest.mark.asyncio
    async def test_cost_zero_without_usage(self):
        driver = ClaudeCodeDriver(enabled=True)
        data = {"result": "Hello", "model": "claude-sonnet-4-6"}
        with patch.object(driver, "_run_cli", new_callable=AsyncMock) as mock_cli:
            mock_cli.return_value = _make_cli_result(data)
            result = await driver.run_task("test")

        assert result.success
        assert result.cost_usd == 0.0

    @pytest.mark.asyncio
    async def test_cost_zero_on_failure(self):
        driver = ClaudeCodeDriver(enabled=True)
        with patch.object(driver, "_run_cli", new_callable=AsyncMock) as mock_cli:
            mock_cli.return_value = CLIResult(returncode=1, stdout="", stderr="error")
            result = await driver.run_task("test")

        assert not result.success
        assert result.cost_usd == 0.0


class TestCodexCLIDriverCost:
    @pytest.mark.asyncio
    async def test_cost_from_usage_metadata(self):
        driver = CodexCLIDriver(enabled=True)
        data = {
            "result": "sorted",
            "model": "o4-mini",
            "usage": {"prompt_tokens": 5000, "completion_tokens": 2000},
        }
        with patch.object(driver, "_run_cli", new_callable=AsyncMock) as mock_cli:
            mock_cli.return_value = _make_cli_result(data)
            result = await driver.run_task("test")

        assert result.success
        assert result.cost_usd > 0.0
        expected = (5000 / 1_000_000) * 1.10 + (2000 / 1_000_000) * 4.40
        assert result.cost_usd == round(expected, 6)


class TestGeminiCLIDriverCost:
    @pytest.mark.asyncio
    async def test_cost_from_usage_metadata(self):
        driver = GeminiCLIDriver(enabled=True)
        data = {
            "result": "analysis",
            "model": "gemini/gemini-2.5-pro",
            "usage": {"prompt_tokens": 10000, "completion_tokens": 3000},
        }
        with patch.object(driver, "_run_cli", new_callable=AsyncMock) as mock_cli:
            mock_cli.return_value = _make_cli_result(data)
            result = await driver.run_task("test")

        assert result.success
        assert result.cost_usd > 0.0
        expected = (10000 / 1_000_000) * 1.25 + (3000 / 1_000_000) * 10.0
        assert result.cost_usd == round(expected, 6)

    @pytest.mark.asyncio
    async def test_cost_zero_without_usage(self):
        driver = GeminiCLIDriver(enabled=True)
        data = {"result": "text only"}
        with patch.object(driver, "_run_cli", new_callable=AsyncMock) as mock_cli:
            mock_cli.return_value = _make_cli_result(data)
            result = await driver.run_task("test")

        assert result.success
        assert result.cost_usd == 0.0
