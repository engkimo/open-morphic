"""Tests for RouteToEngineUseCase — engine selection and execution with fallback."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from application.use_cases.route_to_engine import RouteToEngineUseCase
from domain.ports.agent_engine import AgentEngineCapabilities, AgentEnginePort, AgentEngineResult
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType


def _make_driver(
    engine_type: AgentEngineType = AgentEngineType.OLLAMA,
    available: bool = True,
    success: bool = True,
    output: str = "ok",
    cost_usd: float = 0.0,
    error: str | None = None,
    max_context_tokens: int = 8_000,
    cost_per_hour_usd: float = 0.0,
) -> AsyncMock:
    """Create a mock AgentEnginePort driver."""
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
            success=success,
            output=output,
            cost_usd=cost_usd,
            error=error,
        )
    )
    return driver


def _make_drivers(**overrides: AsyncMock) -> dict[AgentEngineType, AgentEnginePort]:
    """Create a full driver dict with defaults + overrides."""
    defaults: dict[AgentEngineType, AgentEnginePort] = {
        AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA),
        AgentEngineType.CLAUDE_CODE: _make_driver(
            AgentEngineType.CLAUDE_CODE,
            max_context_tokens=200_000,
            cost_per_hour_usd=3.0,
        ),
        AgentEngineType.CODEX_CLI: _make_driver(
            AgentEngineType.CODEX_CLI,
            max_context_tokens=128_000,
            cost_per_hour_usd=2.0,
        ),
        AgentEngineType.GEMINI_CLI: _make_driver(
            AgentEngineType.GEMINI_CLI,
            max_context_tokens=2_000_000,
            cost_per_hour_usd=1.0,
        ),
        AgentEngineType.OPENHANDS: _make_driver(
            AgentEngineType.OPENHANDS,
            max_context_tokens=200_000,
            cost_per_hour_usd=5.0,
        ),
    }
    for key, val in overrides.items():
        defaults[AgentEngineType(key)] = val
    return defaults


@pytest.fixture()
def drivers() -> dict[AgentEngineType, AgentEnginePort]:
    return _make_drivers()


@pytest.fixture()
def use_case(drivers: dict[AgentEngineType, AgentEnginePort]) -> RouteToEngineUseCase:
    return RouteToEngineUseCase(drivers)


# ═══════════════════════════════════════════════════════════════
# list_engines
# ═══════════════════════════════════════════════════════════════


class TestListEngines:
    async def test_returns_all_registered(self, use_case: RouteToEngineUseCase) -> None:
        result = await use_case.list_engines()
        assert len(result) == 5
        types = {r.engine_type for r in result}
        assert AgentEngineType.OLLAMA in types
        assert AgentEngineType.CLAUDE_CODE in types

    async def test_availability_reflects_driver(self) -> None:
        drivers = {
            AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA, available=True),
            AgentEngineType.CLAUDE_CODE: _make_driver(AgentEngineType.CLAUDE_CODE, available=False),
        }
        uc = RouteToEngineUseCase(drivers)
        result = await uc.list_engines()
        by_type = {r.engine_type: r for r in result}
        assert by_type[AgentEngineType.OLLAMA].available is True
        assert by_type[AgentEngineType.CLAUDE_CODE].available is False

    async def test_capabilities_from_driver(self) -> None:
        drivers = {
            AgentEngineType.GEMINI_CLI: _make_driver(
                AgentEngineType.GEMINI_CLI,
                max_context_tokens=2_000_000,
            ),
        }
        uc = RouteToEngineUseCase(drivers)
        result = await uc.list_engines()
        assert result[0].capabilities.max_context_tokens == 2_000_000

    async def test_empty_drivers(self) -> None:
        uc = RouteToEngineUseCase({})
        result = await uc.list_engines()
        assert result == []


# ═══════════════════════════════════════════════════════════════
# get_engine
# ═══════════════════════════════════════════════════════════════


class TestGetEngine:
    async def test_found(self, use_case: RouteToEngineUseCase) -> None:
        result = await use_case.get_engine(AgentEngineType.OLLAMA)
        assert result is not None
        assert result.engine_type == AgentEngineType.OLLAMA

    async def test_not_found(self, use_case: RouteToEngineUseCase) -> None:
        result = await use_case.get_engine(AgentEngineType.ADK)
        assert result is None


# ═══════════════════════════════════════════════════════════════
# execute — happy path
# ═══════════════════════════════════════════════════════════════


class TestExecuteHappy:
    async def test_default_routing_simple_qa(self, use_case: RouteToEngineUseCase) -> None:
        result = await use_case.execute("What is Python?", task_type=TaskType.SIMPLE_QA)
        assert result.success is True
        # SIMPLE_QA routes to OLLAMA by default
        assert result.engine == AgentEngineType.OLLAMA

    async def test_complex_reasoning_routes_to_claude(self, use_case: RouteToEngineUseCase) -> None:
        result = await use_case.execute(
            "Design a microservice architecture",
            task_type=TaskType.COMPLEX_REASONING,
            budget=5.0,
        )
        assert result.success is True
        assert result.engine == AgentEngineType.CLAUDE_CODE

    async def test_long_context_routes_to_gemini(self, use_case: RouteToEngineUseCase) -> None:
        result = await use_case.execute(
            "Analyze this large document",
            task_type=TaskType.LONG_CONTEXT,
            budget=5.0,
            context_tokens=200_000,
        )
        assert result.success is True
        assert result.engine == AgentEngineType.GEMINI_CLI

    async def test_preferred_engine_used_first(self, use_case: RouteToEngineUseCase) -> None:
        result = await use_case.execute(
            "Code review",
            preferred_engine=AgentEngineType.CODEX_CLI,
            budget=5.0,
        )
        assert result.success is True
        assert result.engine == AgentEngineType.CODEX_CLI

    async def test_zero_budget_forces_ollama(self, use_case: RouteToEngineUseCase) -> None:
        result = await use_case.execute("Summarize this", budget=0.0)
        assert result.success is True
        assert result.engine == AgentEngineType.OLLAMA

    async def test_passes_model_and_timeout(self, drivers: dict) -> None:
        uc = RouteToEngineUseCase(drivers)
        await uc.execute(
            "test",
            task_type=TaskType.SIMPLE_QA,
            model="custom-model",
            timeout_seconds=60.0,
        )
        drivers[AgentEngineType.OLLAMA].run_task.assert_awaited_once_with(
            task="test",
            model="custom-model",
            timeout_seconds=60.0,
        )


# ═══════════════════════════════════════════════════════════════
# execute — fallback
# ═══════════════════════════════════════════════════════════════


class TestExecuteFallback:
    async def test_fallback_on_unavailable(self) -> None:
        """Primary engine unavailable → falls back to next in chain."""
        drivers = {
            AgentEngineType.CLAUDE_CODE: _make_driver(AgentEngineType.CLAUDE_CODE, available=False),
            AgentEngineType.CODEX_CLI: _make_driver(AgentEngineType.CODEX_CLI),
            AgentEngineType.GEMINI_CLI: _make_driver(AgentEngineType.GEMINI_CLI),
            AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA),
        }
        uc = RouteToEngineUseCase(drivers)
        result = await uc.execute(
            "test fallback",
            task_type=TaskType.COMPLEX_REASONING,
            budget=5.0,
        )
        assert result.success is True
        assert result.engine == AgentEngineType.CODEX_CLI

    async def test_fallback_on_failure_result(self) -> None:
        """Primary engine returns failure → tries next engine."""
        drivers = {
            AgentEngineType.CLAUDE_CODE: _make_driver(
                AgentEngineType.CLAUDE_CODE, success=False, error="rate limit"
            ),
            AgentEngineType.CODEX_CLI: _make_driver(AgentEngineType.CODEX_CLI),
            AgentEngineType.GEMINI_CLI: _make_driver(AgentEngineType.GEMINI_CLI),
            AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA),
        }
        uc = RouteToEngineUseCase(drivers)
        result = await uc.execute(
            "test fallback",
            task_type=TaskType.COMPLEX_REASONING,
            budget=5.0,
        )
        assert result.success is True
        assert result.engine == AgentEngineType.CODEX_CLI

    async def test_fallback_on_exception(self) -> None:
        """Primary engine raises exception → tries next engine."""
        claude_driver = _make_driver(AgentEngineType.CLAUDE_CODE)
        claude_driver.run_task = AsyncMock(side_effect=RuntimeError("connection lost"))

        drivers = {
            AgentEngineType.CLAUDE_CODE: claude_driver,
            AgentEngineType.CODEX_CLI: _make_driver(AgentEngineType.CODEX_CLI),
            AgentEngineType.GEMINI_CLI: _make_driver(AgentEngineType.GEMINI_CLI),
            AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA),
        }
        uc = RouteToEngineUseCase(drivers)
        result = await uc.execute(
            "test exception fallback",
            task_type=TaskType.COMPLEX_REASONING,
            budget=5.0,
        )
        assert result.success is True
        assert result.engine == AgentEngineType.CODEX_CLI

    async def test_all_engines_fail_returns_last_error(self) -> None:
        """All engines fail → returns last error result."""
        drivers = {
            AgentEngineType.OLLAMA: _make_driver(
                AgentEngineType.OLLAMA, success=False, error="model not loaded"
            ),
        }
        uc = RouteToEngineUseCase(drivers)
        result = await uc.execute("test all fail", budget=0.0)
        assert result.success is False
        assert result.error == "model not loaded"

    async def test_all_engines_unavailable(self) -> None:
        """All engines unavailable → returns generic error."""
        drivers = {
            AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA, available=False),
        }
        uc = RouteToEngineUseCase(drivers)
        result = await uc.execute("test none available", budget=0.0)
        assert result.success is False
        assert result.error == "No engines available"

    async def test_preferred_engine_unavailable_falls_back(self) -> None:
        """Preferred engine unavailable → falls back to router chain."""
        drivers = {
            AgentEngineType.OPENHANDS: _make_driver(AgentEngineType.OPENHANDS, available=False),
            AgentEngineType.CLAUDE_CODE: _make_driver(AgentEngineType.CLAUDE_CODE),
            AgentEngineType.CODEX_CLI: _make_driver(AgentEngineType.CODEX_CLI),
            AgentEngineType.GEMINI_CLI: _make_driver(AgentEngineType.GEMINI_CLI),
            AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA),
        }
        uc = RouteToEngineUseCase(drivers)
        result = await uc.execute(
            "test preferred fallback",
            preferred_engine=AgentEngineType.OPENHANDS,
            budget=5.0,
        )
        assert result.success is True
        # Should fallback to next available
        assert result.engine != AgentEngineType.OPENHANDS

    async def test_unregistered_engine_skipped(self) -> None:
        """Engine in fallback chain but not registered → skipped."""
        # Only OLLAMA registered, but CLAUDE_CODE is primary for COMPLEX_REASONING
        drivers = {
            AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA),
        }
        uc = RouteToEngineUseCase(drivers)
        result = await uc.execute(
            "test skip unregistered",
            task_type=TaskType.COMPLEX_REASONING,
            budget=5.0,
        )
        assert result.success is True
        assert result.engine == AgentEngineType.OLLAMA


# ═══════════════════════════════════════════════════════════════
# _build_chain
# ═══════════════════════════════════════════════════════════════


class TestBuildChain:
    def test_default_chain_has_preferred_first(self) -> None:
        uc = RouteToEngineUseCase({})
        chain = uc._build_chain(
            task_type=TaskType.COMPLEX_REASONING,
            budget=5.0,
            estimated_hours=0.0,
            context_tokens=0,
            preferred_engine=None,
        )
        assert chain[0] == AgentEngineType.CLAUDE_CODE
        assert chain[-1] == AgentEngineType.OLLAMA

    def test_preferred_engine_prepended(self) -> None:
        uc = RouteToEngineUseCase({})
        chain = uc._build_chain(
            task_type=TaskType.SIMPLE_QA,
            budget=5.0,
            estimated_hours=0.0,
            context_tokens=0,
            preferred_engine=AgentEngineType.GEMINI_CLI,
        )
        assert chain[0] == AgentEngineType.GEMINI_CLI

    def test_no_duplicates_in_chain(self) -> None:
        uc = RouteToEngineUseCase({})
        chain = uc._build_chain(
            task_type=TaskType.COMPLEX_REASONING,
            budget=5.0,
            estimated_hours=0.0,
            context_tokens=0,
            preferred_engine=AgentEngineType.CLAUDE_CODE,
        )
        assert len(chain) == len(set(chain))

    def test_zero_budget_chain_only_ollama(self) -> None:
        uc = RouteToEngineUseCase({})
        chain = uc._build_chain(
            task_type=TaskType.COMPLEX_REASONING,
            budget=0.0,
            estimated_hours=0.0,
            context_tokens=0,
            preferred_engine=None,
        )
        assert chain == [AgentEngineType.OLLAMA]
