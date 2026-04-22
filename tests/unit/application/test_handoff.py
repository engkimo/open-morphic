"""Tests for HandoffTaskUseCase — cross-agent task handoff with state preservation.

Sprint 7.4: Affinity-Aware Routing + Task Handoff
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from application.use_cases.handoff_task import HandoffRequest, HandoffTaskUseCase
from domain.entities.cognitive import Decision, SharedTaskState
from domain.ports.agent_engine import AgentEngineResult
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType


def _make_engine_result(
    engine: AgentEngineType = AgentEngineType.GEMINI_CLI,
    success: bool = True,
    output: str = "result output",
    cost_usd: float = 0.01,
) -> AgentEngineResult:
    return AgentEngineResult(
        engine=engine,
        success=success,
        output=output,
        cost_usd=cost_usd,
    )


def _make_request(
    task: str = "Analyze the codebase",
    task_id: str = "task-1",
    source_engine: AgentEngineType = AgentEngineType.CLAUDE_CODE,
    target_engine: AgentEngineType | None = AgentEngineType.GEMINI_CLI,
    reason: str = "Need long context window",
    **kwargs,
) -> HandoffRequest:
    return HandoffRequest(
        task=task,
        task_id=task_id,
        source_engine=source_engine,
        target_engine=target_engine,
        reason=reason,
        **kwargs,
    )


def _make_use_case(
    route_result: AgentEngineResult | None = None,
    existing_state: SharedTaskState | None = None,
    adapters: dict | None = None,
    insight_extractor: object | None = None,
) -> tuple[HandoffTaskUseCase, AsyncMock, AsyncMock]:
    """Create HandoffTaskUseCase with mocked dependencies."""
    route_to_engine = AsyncMock()
    route_to_engine.execute = AsyncMock(return_value=route_result or _make_engine_result())

    task_state_repo = AsyncMock()
    task_state_repo.get = AsyncMock(return_value=existing_state)
    task_state_repo.save = AsyncMock()
    task_state_repo.append_action = AsyncMock()

    uc = HandoffTaskUseCase(
        route_to_engine=route_to_engine,
        task_state_repo=task_state_repo,
        context_adapters=adapters,
        insight_extractor=insight_extractor,
    )
    return uc, route_to_engine, task_state_repo


# ═══════════════════════════════════════════════════════════════
# Happy Path
# ═══════════════════════════════════════════════════════════════


class TestHandoffHappyPath:
    async def test_successful_handoff(self) -> None:
        uc, route_mock, state_repo = _make_use_case()
        result = await uc.handoff(_make_request())
        assert result.success is True
        assert result.source_engine == AgentEngineType.CLAUDE_CODE
        assert result.target_engine == AgentEngineType.GEMINI_CLI
        assert result.engine_result is not None

    async def test_decisions_preserved_in_state(self) -> None:
        uc, _, state_repo = _make_use_case()
        result = await uc.handoff(_make_request())
        assert result.state is not None
        assert len(result.state.decisions) == 1
        assert "Handoff" in result.state.decisions[0].description

    async def test_artifacts_merged(self) -> None:
        uc, _, state_repo = _make_use_case()
        request = _make_request(artifacts={"report": "v1 content", "data": "some data"})
        result = await uc.handoff(request)
        assert result.state is not None
        assert result.state.artifacts["report"] == "v1 content"
        assert result.state.artifacts["data"] == "some data"

    async def test_agent_history_has_handoff_actions(self) -> None:
        uc, _, state_repo = _make_use_case()
        result = await uc.handoff(_make_request())
        assert result.state is not None
        actions = result.state.agent_history
        assert len(actions) == 2  # handoff + received_handoff
        assert actions[0].action_type == "handoff"
        assert actions[0].agent_engine == AgentEngineType.CLAUDE_CODE
        assert actions[1].action_type == "received_handoff"
        assert actions[1].agent_engine == AgentEngineType.GEMINI_CLI

    async def test_state_persisted_twice(self) -> None:
        """State is saved once before execution and once after."""
        uc, _, state_repo = _make_use_case()
        await uc.handoff(_make_request())
        assert state_repo.save.await_count == 2


# ═══════════════════════════════════════════════════════════════
# State Creation and Reuse
# ═══════════════════════════════════════════════════════════════


class TestHandoffStateManagement:
    async def test_creates_new_state_if_none_exists(self) -> None:
        uc, _, state_repo = _make_use_case(existing_state=None)
        result = await uc.handoff(_make_request())
        assert result.state is not None
        assert result.state.task_id == "task-1"

    async def test_reuses_existing_state(self) -> None:
        existing = SharedTaskState(task_id="task-1")
        existing.add_decision(
            Decision(
                description="Prior decision",
                rationale="earlier",
                agent_engine=AgentEngineType.OLLAMA,
            )
        )
        existing.add_artifact("old_key", "old_value")
        uc, _, state_repo = _make_use_case(existing_state=existing)
        result = await uc.handoff(_make_request())
        assert result.state is not None
        # Prior decision + new handoff decision
        assert len(result.state.decisions) == 2
        assert result.state.artifacts["old_key"] == "old_value"

    async def test_blockers_preserved(self) -> None:
        existing = SharedTaskState(task_id="task-1")
        existing.add_blocker("API rate limit")
        uc, _, _ = _make_use_case(existing_state=existing)
        result = await uc.handoff(_make_request())
        assert result.state is not None
        assert "API rate limit" in result.state.blockers


# ═══════════════════════════════════════════════════════════════
# Target Selection
# ═══════════════════════════════════════════════════════════════


class TestHandoffTargetSelection:
    async def test_specified_target_passed_to_router(self) -> None:
        uc, route_mock, _ = _make_use_case()
        await uc.handoff(_make_request(target_engine=AgentEngineType.CODEX_CLI))
        call_kwargs = route_mock.execute.call_args[1]
        assert call_kwargs["preferred_engine"] == AgentEngineType.CODEX_CLI

    async def test_none_target_lets_router_decide(self) -> None:
        uc, route_mock, _ = _make_use_case()
        await uc.handoff(_make_request(target_engine=None))
        call_kwargs = route_mock.execute.call_args[1]
        assert call_kwargs["preferred_engine"] is None

    async def test_actual_target_recorded_in_result(self) -> None:
        """If router picks a different engine, result reflects that."""
        engine_result = _make_engine_result(engine=AgentEngineType.CODEX_CLI)
        uc, _, _ = _make_use_case(route_result=engine_result)
        result = await uc.handoff(_make_request(target_engine=AgentEngineType.GEMINI_CLI))
        # Router returned CODEX_CLI instead of requested GEMINI_CLI
        assert result.target_engine == AgentEngineType.CODEX_CLI

    async def test_task_type_and_budget_passed(self) -> None:
        uc, route_mock, _ = _make_use_case()
        await uc.handoff(
            _make_request(
                task_type=TaskType.LONG_CONTEXT,
                budget=10.0,
            )
        )
        call_kwargs = route_mock.execute.call_args[1]
        assert call_kwargs["task_type"] == TaskType.LONG_CONTEXT
        assert call_kwargs["budget"] == 10.0


# ═══════════════════════════════════════════════════════════════
# Context Injection
# ═══════════════════════════════════════════════════════════════


class TestHandoffContextInjection:
    async def test_adapter_used_when_available(self) -> None:
        adapter = MagicMock()
        adapter.inject_context.return_value = "## Adapter Injected"
        adapters = {AgentEngineType.GEMINI_CLI: adapter}
        uc, route_mock, _ = _make_use_case(adapters=adapters)
        await uc.handoff(_make_request())
        call_kwargs = route_mock.execute.call_args[1]
        assert "Adapter Injected" in call_kwargs["context"]

    async def test_fallback_context_without_adapter(self) -> None:
        uc, route_mock, _ = _make_use_case()
        await uc.handoff(_make_request())
        call_kwargs = route_mock.execute.call_args[1]
        assert "Handoff Context" in call_kwargs["context"]

    async def test_fallback_context_includes_decisions(self) -> None:
        existing = SharedTaskState(task_id="task-1")
        existing.add_decision(
            Decision(
                description="Use REST API",
                rationale="consistency",
                agent_engine=AgentEngineType.CLAUDE_CODE,
            )
        )
        uc, route_mock, _ = _make_use_case(existing_state=existing)
        await uc.handoff(_make_request())
        call_kwargs = route_mock.execute.call_args[1]
        assert "Prior Decisions" in call_kwargs["context"]


# ═══════════════════════════════════════════════════════════════
# Insight Extraction
# ═══════════════════════════════════════════════════════════════


class TestHandoffInsightExtraction:
    async def test_extracts_when_requested(self) -> None:
        extractor = AsyncMock()
        extractor.extract_and_store = AsyncMock(return_value=[])
        uc, _, _ = _make_use_case(insight_extractor=extractor)
        await uc.handoff(_make_request(extract_insights=True))
        extractor.extract_and_store.assert_awaited_once()

    async def test_skips_when_not_requested(self) -> None:
        extractor = AsyncMock()
        uc, _, _ = _make_use_case(insight_extractor=extractor)
        await uc.handoff(_make_request(extract_insights=False))
        extractor.extract_and_store.assert_not_awaited()

    async def test_skips_on_failure_result(self) -> None:
        engine_result = _make_engine_result(success=False)
        extractor = AsyncMock()
        uc, _, _ = _make_use_case(route_result=engine_result, insight_extractor=extractor)
        await uc.handoff(_make_request(extract_insights=True))
        extractor.extract_and_store.assert_not_awaited()

    async def test_extraction_error_swallowed(self) -> None:
        extractor = AsyncMock()
        extractor.extract_and_store = AsyncMock(side_effect=RuntimeError("extraction failed"))
        uc, _, _ = _make_use_case(insight_extractor=extractor)
        result = await uc.handoff(_make_request(extract_insights=True))
        assert result.success is True


# ═══════════════════════════════════════════════════════════════
# Failure Handling
# ═══════════════════════════════════════════════════════════════


class TestHandoffFailureHandling:
    async def test_engine_failure_propagated(self) -> None:
        engine_result = _make_engine_result(success=False, output="error")
        uc, _, _ = _make_use_case(route_result=engine_result)
        result = await uc.handoff(_make_request())
        assert result.success is False
        assert result.engine_result is not None

    async def test_repo_error_returns_failure(self) -> None:
        uc, _, state_repo = _make_use_case()
        state_repo.get = AsyncMock(side_effect=RuntimeError("DB down"))
        result = await uc.handoff(_make_request())
        assert result.success is False
        assert result.error is not None

    async def test_route_error_returns_failure(self) -> None:
        uc, route_mock, _ = _make_use_case()
        route_mock.execute = AsyncMock(side_effect=RuntimeError("Route failed"))
        result = await uc.handoff(_make_request())
        assert result.success is False
        assert "Route failed" in (result.error or "")

    async def test_failure_result_includes_source_engine(self) -> None:
        uc, route_mock, _ = _make_use_case()
        route_mock.execute = AsyncMock(side_effect=RuntimeError("fail"))
        result = await uc.handoff(_make_request())
        assert result.source_engine == AgentEngineType.CLAUDE_CODE
