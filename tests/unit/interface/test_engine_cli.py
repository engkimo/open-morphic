"""Tests for Engine CLI commands — Sprint 4.3."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from typer.testing import CliRunner

from application.use_cases.route_to_engine import RouteToEngineUseCase
from domain.ports.agent_engine import AgentEngineCapabilities, AgentEnginePort, AgentEngineResult
from domain.value_objects.agent_engine import AgentEngineType
from interface.cli import _utils as cli_utils
from interface.cli.main import app

runner = CliRunner()


def _make_driver(
    engine_type: AgentEngineType = AgentEngineType.OLLAMA,
    available: bool = True,
    max_context_tokens: int = 8_000,
    cost_per_hour_usd: float = 0.0,
) -> AsyncMock:
    driver = AsyncMock(spec=AgentEnginePort)
    driver.is_available = AsyncMock(return_value=available)
    driver.get_capabilities.return_value = AgentEngineCapabilities(
        engine_type=engine_type,
        max_context_tokens=max_context_tokens,
        cost_per_hour_usd=cost_per_hour_usd,
    )
    driver.run_task = AsyncMock(
        return_value=AgentEngineResult(
            engine=engine_type,
            success=True,
            output="result text",
            cost_usd=0.001,
            duration_seconds=1.5,
        )
    )
    return driver


class _MockContainer:
    def __init__(self) -> None:
        drivers: dict[AgentEngineType, AgentEnginePort] = {
            AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA),
            AgentEngineType.CLAUDE_CODE: _make_driver(
                AgentEngineType.CLAUDE_CODE,
                available=False,
                max_context_tokens=200_000,
                cost_per_hour_usd=3.0,
            ),
        }
        self.route_to_engine = RouteToEngineUseCase(drivers)
        self.agent_drivers = drivers


@pytest.fixture(autouse=True)
def _inject_container(monkeypatch: pytest.MonkeyPatch) -> _MockContainer:
    container = _MockContainer()
    monkeypatch.setattr(cli_utils, "_container_instance", container)
    return container


@pytest.fixture()
def container(_inject_container: _MockContainer) -> _MockContainer:
    return _inject_container


class TestEngineList:
    def test_list_shows_engines(self) -> None:
        result = runner.invoke(app, ["engine", "list"])
        assert result.exit_code == 0
        assert "ollama" in result.output
        assert "claude_code" in result.output

    def test_list_shows_availability(self) -> None:
        result = runner.invoke(app, ["engine", "list"])
        assert result.exit_code == 0
        assert "Yes" in result.output
        assert "No" in result.output

    def test_list_shows_free(self) -> None:
        result = runner.invoke(app, ["engine", "list"])
        assert result.exit_code == 0
        assert "FREE" in result.output


class TestEngineRun:
    def test_run_simple(self) -> None:
        result = runner.invoke(app, ["engine", "run", "Hello world"])
        assert result.exit_code == 0
        assert "ollama" in result.output
        assert "Success" in result.output

    def test_run_with_engine_flag(self, container: _MockContainer) -> None:
        # Make claude_code available
        container.agent_drivers[AgentEngineType.CLAUDE_CODE].is_available = AsyncMock(
            return_value=True
        )
        result = runner.invoke(
            app, ["engine", "run", "Analyze code", "--engine", "claude_code", "--budget", "5"]
        )
        assert result.exit_code == 0
        assert "claude_code" in result.output

    def test_run_unknown_engine(self) -> None:
        result = runner.invoke(app, ["engine", "run", "Test", "--engine", "fake"])
        assert result.exit_code == 1
        assert "Unknown engine" in result.output

    def test_run_unknown_task_type(self) -> None:
        result = runner.invoke(app, ["engine", "run", "Test", "--type", "bogus"])
        assert result.exit_code == 1
        assert "Unknown task type" in result.output

    def test_run_shows_cost_and_duration(self) -> None:
        result = runner.invoke(app, ["engine", "run", "Quick test"])
        assert result.exit_code == 0
        assert "$0.0010" in result.output
        assert "1.5s" in result.output
