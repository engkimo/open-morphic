"""Tests for morphic doctor CLI command — Sprint 23.1 + 24.1."""

from __future__ import annotations

import subprocess as real_subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from application.use_cases.route_to_engine import RouteToEngineUseCase
from domain.ports.agent_engine import AgentEngineCapabilities, AgentEnginePort
from domain.value_objects.agent_engine import AgentEngineType
from interface.cli import _utils as cli_utils
from interface.cli.commands.doctor import _check_docker, _check_openhands
from interface.cli.main import app

runner = CliRunner()


class _MockSettings:
    """Minimal settings for doctor tests."""

    claude_code_cli_path: str = "claude"
    gemini_cli_path: str = "gemini"
    codex_cli_path: str = "codex"
    has_anthropic: bool = True
    has_openai: bool = False
    has_gemini: bool = True
    use_postgres: bool = False
    use_sqlite: bool = False


class _MockOllama:
    async def is_running(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["qwen3:8b", "deepseek-r1:8b"]


def _make_driver(
    engine_type: AgentEngineType = AgentEngineType.OLLAMA,
    available: bool = True,
) -> AsyncMock:
    driver = AsyncMock(spec=AgentEnginePort)
    driver.is_available = AsyncMock(return_value=available)
    driver.get_capabilities.return_value = AgentEngineCapabilities(
        engine_type=engine_type,
        max_context_tokens=8_000,
    )
    return driver


class _MockContainer:
    def __init__(self) -> None:
        drivers = {
            AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA),
            AgentEngineType.CLAUDE_CODE: _make_driver(AgentEngineType.CLAUDE_CODE, available=False),
        }
        self.route_to_engine = RouteToEngineUseCase(drivers)
        self.agent_drivers = drivers
        self.ollama = _MockOllama()
        self.settings = _MockSettings()


@pytest.fixture(autouse=True)
def _inject_container(monkeypatch: pytest.MonkeyPatch) -> _MockContainer:
    container = _MockContainer()
    monkeypatch.setattr(cli_utils, "_container_instance", container)
    return container


class TestDoctorCheck:
    def test_runs_successfully(self) -> None:
        result = runner.invoke(app, ["doctor", "check"])
        assert result.exit_code == 0
        assert "Ollama" in result.output

    def test_shows_ok_status(self) -> None:
        result = runner.invoke(app, ["doctor", "check"])
        assert "OK" in result.output

    def test_shows_warn_for_unavailable_engine(self) -> None:
        result = runner.invoke(app, ["doctor", "check"])
        # claude_code is unavailable → should show WARN
        assert "WARN" in result.output

    def test_shows_api_key_status(self) -> None:
        result = runner.invoke(app, ["doctor", "check"])
        assert "Anthropic" in result.output
        assert "OpenAI" in result.output
        assert "Gemini" in result.output

    def test_shows_database_mode(self) -> None:
        result = runner.invoke(app, ["doctor", "check"])
        assert "Database" in result.output
        assert "In-Memory" in result.output

    def test_shows_summary_counts(self) -> None:
        result = runner.invoke(app, ["doctor", "check"])
        # Should have OK and WARN counts
        assert "OK" in result.output

    def test_ollama_down_shows_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        container = _MockContainer()
        container.ollama = MagicMock()
        container.ollama.is_running = AsyncMock(return_value=False)
        monkeypatch.setattr(cli_utils, "_container_instance", container)
        result = runner.invoke(app, ["doctor", "check"])
        assert "FAIL" in result.output
        # Exit code 1 when there are failures
        assert result.exit_code == 1

    def test_shows_ollama_models(self) -> None:
        result = runner.invoke(app, ["doctor", "check"])
        assert "qwen3:8b" in result.output

    def test_shows_docker_status(self) -> None:
        result = runner.invoke(app, ["doctor", "check"])
        assert "Docker" in result.output

    def test_shows_openhands_status(self) -> None:
        result = runner.invoke(app, ["doctor", "check"])
        assert "OpenHands" in result.output


# ── Docker check unit tests ──


class TestDockerCheck:
    def test_docker_running_with_image(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),
                MagicMock(returncode=0, stdout="ghcr.io/all-hands-ai/openhands:latest\n"),
            ]
            result = _check_docker()
        assert result.status == "OK"
        assert "OpenHands image" in result.message

    def test_docker_running_no_image(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),
                MagicMock(returncode=0, stdout=""),
            ]
            result = _check_docker()
        assert result.status == "OK"
        assert "not pulled" in result.message

    def test_docker_not_running(self) -> None:
        with patch("subprocess.run", return_value=MagicMock(returncode=1)):
            result = _check_docker()
        assert result.status == "WARN"
        assert "not running" in result.message.lower()

    def test_docker_cli_not_found(self) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = _check_docker()
        assert result.status == "WARN"
        assert "not found" in result.message.lower()

    def test_docker_timeout(self) -> None:
        with patch(
            "subprocess.run",
            side_effect=real_subprocess.TimeoutExpired(cmd="docker info", timeout=10),
        ):
            result = _check_docker()
        assert result.status == "WARN"
        assert "timed out" in result.message.lower()


# ── OpenHands check unit tests ──


class TestOpenHandsCheck:
    @pytest.mark.asyncio
    async def test_openhands_available(self) -> None:
        mock_driver = AsyncMock()
        mock_driver.is_available.return_value = True
        container = MagicMock()
        container.agent_drivers = MagicMock()
        container.agent_drivers.get.return_value = mock_driver
        result = await _check_openhands(container)
        assert result.status == "OK"
        assert "reachable" in result.message.lower()

    @pytest.mark.asyncio
    async def test_openhands_unavailable(self) -> None:
        mock_driver = AsyncMock()
        mock_driver.is_available.return_value = False
        container = MagicMock()
        container.agent_drivers = MagicMock()
        container.agent_drivers.get.return_value = mock_driver
        result = await _check_openhands(container)
        assert result.status == "WARN"
        assert "unreachable" in result.message.lower()

    @pytest.mark.asyncio
    async def test_openhands_no_driver(self) -> None:
        container = MagicMock()
        container.agent_drivers = MagicMock()
        container.agent_drivers.get.return_value = None
        result = await _check_openhands(container)
        assert result.status == "WARN"
        assert "not wired" in result.message.lower()
