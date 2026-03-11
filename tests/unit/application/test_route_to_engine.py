"""Tests for RouteToEngineUseCase — engine selection and execution with fallback.

Sprint 4.3: Base routing and execution
Sprint 7.4: Affinity-aware routing, adapter context injection, action recording
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from application.use_cases.route_to_engine import RouteToEngineUseCase
from domain.entities.cognitive import AgentAffinityScore, SharedTaskState
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


def _make_affinity(
    engine: AgentEngineType = AgentEngineType.GEMINI_CLI,
    topic: str = "general",
    familiarity: float = 0.8,
    recency: float = 0.7,
    success_rate: float = 0.9,
    cost_efficiency: float = 0.6,
    sample_count: int = 10,
) -> AgentAffinityScore:
    return AgentAffinityScore(
        engine=engine,
        topic=topic,
        familiarity=familiarity,
        recency=recency,
        success_rate=success_rate,
        cost_efficiency=cost_efficiency,
        sample_count=sample_count,
    )


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
    async def test_default_chain_has_preferred_first(self) -> None:
        uc = RouteToEngineUseCase({})
        chain = await uc._build_chain(
            task_type=TaskType.COMPLEX_REASONING,
            budget=5.0,
            estimated_hours=0.0,
            context_tokens=0,
            preferred_engine=None,
        )
        assert chain[0] == AgentEngineType.CLAUDE_CODE
        assert chain[-1] == AgentEngineType.OLLAMA

    async def test_preferred_engine_prepended(self) -> None:
        uc = RouteToEngineUseCase({})
        chain = await uc._build_chain(
            task_type=TaskType.SIMPLE_QA,
            budget=5.0,
            estimated_hours=0.0,
            context_tokens=0,
            preferred_engine=AgentEngineType.GEMINI_CLI,
        )
        assert chain[0] == AgentEngineType.GEMINI_CLI

    async def test_no_duplicates_in_chain(self) -> None:
        uc = RouteToEngineUseCase({})
        chain = await uc._build_chain(
            task_type=TaskType.COMPLEX_REASONING,
            budget=5.0,
            estimated_hours=0.0,
            context_tokens=0,
            preferred_engine=AgentEngineType.CLAUDE_CODE,
        )
        assert len(chain) == len(set(chain))

    async def test_zero_budget_chain_only_ollama(self) -> None:
        uc = RouteToEngineUseCase({})
        chain = await uc._build_chain(
            task_type=TaskType.COMPLEX_REASONING,
            budget=0.0,
            estimated_hours=0.0,
            context_tokens=0,
            preferred_engine=None,
        )
        assert chain == [AgentEngineType.OLLAMA]


# ═══════════════════════════════════════════════════════════════
# execute — context injection (Sprint 4.6)
# ═══════════════════════════════════════════════════════════════


class TestContextInjection:
    async def test_context_prepended_to_task(self, drivers: dict) -> None:
        """When context is provided, it should be prepended to the task string."""
        uc = RouteToEngineUseCase(drivers)
        await uc.execute(
            "Write tests",
            task_type=TaskType.SIMPLE_QA,
            context="Use pytest framework",
        )
        call_kwargs = drivers[AgentEngineType.OLLAMA].run_task.call_args
        effective_task = call_kwargs[1]["task"]
        assert "Use pytest framework" in effective_task
        assert "Write tests" in effective_task
        assert "---" in effective_task

    async def test_no_context_passes_task_unchanged(self, drivers: dict) -> None:
        """When context is None, task string is passed as-is."""
        uc = RouteToEngineUseCase(drivers)
        await uc.execute(
            "Write tests",
            task_type=TaskType.SIMPLE_QA,
        )
        call_kwargs = drivers[AgentEngineType.OLLAMA].run_task.call_args
        assert call_kwargs[1]["task"] == "Write tests"

    async def test_empty_context_passes_task_unchanged(self, drivers: dict) -> None:
        """Empty string context should not modify the task."""
        uc = RouteToEngineUseCase(drivers)
        await uc.execute(
            "Write tests",
            task_type=TaskType.SIMPLE_QA,
            context="",
        )
        call_kwargs = drivers[AgentEngineType.OLLAMA].run_task.call_args
        assert call_kwargs[1]["task"] == "Write tests"

    async def test_context_with_fallback_still_prepended(self) -> None:
        """Context prepending survives engine fallback."""
        drivers = {
            AgentEngineType.CLAUDE_CODE: _make_driver(AgentEngineType.CLAUDE_CODE, available=False),
            AgentEngineType.CODEX_CLI: _make_driver(AgentEngineType.CODEX_CLI),
            AgentEngineType.GEMINI_CLI: _make_driver(AgentEngineType.GEMINI_CLI),
            AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA),
        }
        uc = RouteToEngineUseCase(drivers)
        result = await uc.execute(
            "Analyze code",
            task_type=TaskType.COMPLEX_REASONING,
            budget=5.0,
            context="Project uses Clean Architecture",
        )
        assert result.success is True
        call_kwargs = drivers[AgentEngineType.CODEX_CLI].run_task.call_args
        effective_task = call_kwargs[1]["task"]
        assert "Project uses Clean Architecture" in effective_task
        assert "Analyze code" in effective_task


# ═══════════════════════════════════════════════════════════════
# Affinity-Aware Routing (Sprint 7.4)
# ═══════════════════════════════════════════════════════════════


class TestAffinityAwareRouting:
    """Affinity data influences engine selection."""

    async def test_affinity_promotes_engine(self) -> None:
        """High affinity for Gemini promotes it over default Claude Code."""
        affinity_repo = AsyncMock()
        affinity_repo.get_by_topic = AsyncMock(
            return_value=[_make_affinity(AgentEngineType.GEMINI_CLI)]
        )
        drivers = _make_drivers()
        uc = RouteToEngineUseCase(drivers, affinity_repo=affinity_repo)
        result = await uc.execute(
            "Analyze code",
            task_type=TaskType.COMPLEX_REASONING,
            budget=5.0,
        )
        assert result.success is True
        assert result.engine == AgentEngineType.GEMINI_CLI

    async def test_no_affinity_repo_uses_default(self) -> None:
        """Without affinity repo, behaves as before."""
        drivers = _make_drivers()
        uc = RouteToEngineUseCase(drivers)
        result = await uc.execute(
            "Design architecture",
            task_type=TaskType.COMPLEX_REASONING,
            budget=5.0,
        )
        assert result.engine == AgentEngineType.CLAUDE_CODE

    async def test_preferred_engine_overrides_affinity(self) -> None:
        """Explicit preferred_engine takes precedence over affinity."""
        affinity_repo = AsyncMock()
        affinity_repo.get_by_topic = AsyncMock(
            return_value=[_make_affinity(AgentEngineType.GEMINI_CLI)]
        )
        drivers = _make_drivers()
        uc = RouteToEngineUseCase(drivers, affinity_repo=affinity_repo)
        result = await uc.execute(
            "Review code",
            preferred_engine=AgentEngineType.CODEX_CLI,
            budget=5.0,
        )
        assert result.engine == AgentEngineType.CODEX_CLI

    async def test_affinity_repo_error_falls_back_gracefully(self) -> None:
        """If affinity repo raises, falls back to base routing."""
        affinity_repo = AsyncMock()
        affinity_repo.get_by_topic = AsyncMock(side_effect=RuntimeError("DB error"))
        drivers = _make_drivers()
        uc = RouteToEngineUseCase(drivers, affinity_repo=affinity_repo)
        result = await uc.execute(
            "Something",
            task_type=TaskType.COMPLEX_REASONING,
            budget=5.0,
        )
        assert result.success is True
        assert result.engine == AgentEngineType.CLAUDE_CODE


# ═══════════════════════════════════════════════════════════════
# Adapter Context Injection (Sprint 7.4)
# ═══════════════════════════════════════════════════════════════


class TestAdapterContextInjection:
    """ContextAdapterPort.inject_context() replaces simple string prepend."""

    async def test_adapter_inject_used_when_available(self) -> None:
        """When adapter, task_state_repo, and task_id are provided, uses adapter."""
        adapter = MagicMock()
        adapter.inject_context.return_value = "## Injected Context\nSome state"
        task_state_repo = AsyncMock()
        task_state_repo.get = AsyncMock(return_value=SharedTaskState(task_id="t1"))

        drivers = {AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA)}
        uc = RouteToEngineUseCase(
            drivers,
            context_adapters={AgentEngineType.OLLAMA: adapter},
            task_state_repo=task_state_repo,
        )
        await uc.execute("Do something", task_id="t1")
        call_kwargs = drivers[AgentEngineType.OLLAMA].run_task.call_args
        assert "Injected Context" in call_kwargs[1]["task"]

    async def test_no_task_id_falls_back_to_simple(self) -> None:
        """Without task_id, adapter is not used even if available."""
        adapter = MagicMock()
        task_state_repo = AsyncMock()

        drivers = {AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA)}
        uc = RouteToEngineUseCase(
            drivers,
            context_adapters={AgentEngineType.OLLAMA: adapter},
            task_state_repo=task_state_repo,
        )
        await uc.execute("Do something", context="plain context")
        adapter.inject_context.assert_not_called()

    async def test_no_state_found_falls_back(self) -> None:
        """When SharedTaskState not found, falls back to simple prepend."""
        adapter = MagicMock()
        task_state_repo = AsyncMock()
        task_state_repo.get = AsyncMock(return_value=None)

        drivers = {AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA)}
        uc = RouteToEngineUseCase(
            drivers,
            context_adapters={AgentEngineType.OLLAMA: adapter},
            task_state_repo=task_state_repo,
        )
        await uc.execute("Do something", task_id="t1", context="fallback ctx")
        call_kwargs = drivers[AgentEngineType.OLLAMA].run_task.call_args
        assert "fallback ctx" in call_kwargs[1]["task"]
        adapter.inject_context.assert_not_called()

    async def test_adapter_receives_context_as_memory(self) -> None:
        """The context param is passed as memory_context to the adapter."""
        adapter = MagicMock()
        adapter.inject_context.return_value = "injected"
        task_state_repo = AsyncMock()
        task_state_repo.get = AsyncMock(return_value=SharedTaskState(task_id="t1"))

        drivers = {AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA)}
        uc = RouteToEngineUseCase(
            drivers,
            context_adapters={AgentEngineType.OLLAMA: adapter},
            task_state_repo=task_state_repo,
        )
        await uc.execute("Do work", task_id="t1", context="memory stuff")
        adapter.inject_context.assert_called_once()
        call_kwargs = adapter.inject_context.call_args
        assert call_kwargs[1]["memory_context"] == "memory stuff"


# ═══════════════════════════════════════════════════════════════
# Affinity Update (Sprint 7.4)
# ═══════════════════════════════════════════════════════════════


class TestAffinityUpdate:
    """Post-success affinity score updates."""

    async def test_creates_new_affinity_on_first_success(self) -> None:
        affinity_repo = AsyncMock()
        affinity_repo.get_by_topic = AsyncMock(return_value=[])
        affinity_repo.get = AsyncMock(return_value=None)
        affinity_repo.upsert = AsyncMock()
        drivers = {AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA)}
        uc = RouteToEngineUseCase(drivers, affinity_repo=affinity_repo)
        await uc.execute("simple task")
        affinity_repo.upsert.assert_awaited_once()
        score = affinity_repo.upsert.call_args[0][0]
        assert score.engine == AgentEngineType.OLLAMA
        assert score.sample_count == 1

    async def test_updates_existing_affinity(self) -> None:
        existing = _make_affinity(AgentEngineType.OLLAMA, topic="general", sample_count=5)
        affinity_repo = AsyncMock()
        affinity_repo.get_by_topic = AsyncMock(return_value=[])
        affinity_repo.get = AsyncMock(return_value=existing)
        affinity_repo.upsert = AsyncMock()
        drivers = {AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA)}
        uc = RouteToEngineUseCase(drivers, affinity_repo=affinity_repo)
        await uc.execute("simple task")
        affinity_repo.upsert.assert_awaited_once()
        score = affinity_repo.upsert.call_args[0][0]
        assert score.sample_count == 6

    async def test_no_affinity_repo_no_error(self) -> None:
        """Without affinity repo, success still works."""
        drivers = {AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA)}
        uc = RouteToEngineUseCase(drivers)
        result = await uc.execute("simple task")
        assert result.success is True

    async def test_affinity_update_error_swallowed(self) -> None:
        """Affinity update error doesn't break execution."""
        affinity_repo = AsyncMock()
        affinity_repo.get_by_topic = AsyncMock(return_value=[])
        affinity_repo.get = AsyncMock(side_effect=RuntimeError("write error"))
        affinity_repo.upsert = AsyncMock()
        drivers = {AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA)}
        uc = RouteToEngineUseCase(drivers, affinity_repo=affinity_repo)
        result = await uc.execute("simple task")
        assert result.success is True


# ═══════════════════════════════════════════════════════════════
# Action Recording (Sprint 7.4)
# ═══════════════════════════════════════════════════════════════


class TestActionRecording:
    """Post-success action recording to SharedTaskState."""

    async def test_records_action_on_success(self) -> None:
        task_state_repo = AsyncMock()
        task_state_repo.append_action = AsyncMock()
        drivers = {AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA)}
        uc = RouteToEngineUseCase(drivers, task_state_repo=task_state_repo)
        await uc.execute("task", task_id="t1")
        task_state_repo.append_action.assert_awaited_once()
        call_args = task_state_repo.append_action.call_args
        assert call_args[0][0] == "t1"
        action = call_args[0][1]
        assert action.agent_engine == AgentEngineType.OLLAMA
        assert action.action_type == "execute"

    async def test_no_task_id_no_recording(self) -> None:
        task_state_repo = AsyncMock()
        drivers = {AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA)}
        uc = RouteToEngineUseCase(drivers, task_state_repo=task_state_repo)
        await uc.execute("task")
        task_state_repo.append_action.assert_not_awaited()

    async def test_no_repo_no_recording(self) -> None:
        drivers = {AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA)}
        uc = RouteToEngineUseCase(drivers)
        result = await uc.execute("task", task_id="t1")
        assert result.success is True

    async def test_recording_error_swallowed(self) -> None:
        task_state_repo = AsyncMock()
        task_state_repo.append_action = AsyncMock(side_effect=RuntimeError("DB error"))
        drivers = {AgentEngineType.OLLAMA: _make_driver(AgentEngineType.OLLAMA)}
        uc = RouteToEngineUseCase(drivers, task_state_repo=task_state_repo)
        result = await uc.execute("task", task_id="t1")
        assert result.success is True
