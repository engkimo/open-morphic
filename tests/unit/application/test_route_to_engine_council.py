"""RouteToEngineUseCase council branch — RED gate per tasks T-15."""

from __future__ import annotations

import pytest

from application.use_cases.route_to_engine import RouteToEngineUseCase
from application.use_cases.run_council_debate import RunCouncilDebateUseCase
from domain.entities.cognitive import Decision, SharedTaskState
from domain.entities.council import Argument
from domain.services.agent_engine_router import AgentEngineRouter
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType
from tests.unit.application._fakes.fake_council_debate import FakeCouncilDebate
from tests.unit.application._fakes.in_memory_event_bus import FakeEventBus


def _arg(engine: AgentEngineType) -> Argument:
    return Argument(
        engine=engine,
        capability_claim="cap",
        cost_claim="cost",
        risk_claim="risk",
        recommended_approach="approach",
    )


def _baseline_chain() -> list[AgentEngineType]:
    return AgentEngineRouter.select_with_fallbacks(
        task_type=TaskType.CODE_GENERATION,
        budget=1.0,
        estimated_hours=0.0,
        context_tokens=0,
    )


@pytest.mark.asyncio
async def test_council_disabled_chain_unchanged() -> None:
    uc = RouteToEngineUseCase(drivers={}, council_enabled=False)
    chain = await uc._build_chain(
        task_type=TaskType.CODE_GENERATION,
        budget=1.0,
        estimated_hours=0.0,
        context_tokens=0,
        preferred_engine=None,
        topic="general",
        task="write a python function",
        task_id=None,
    )
    assert chain == _baseline_chain()


@pytest.mark.asyncio
async def test_council_enabled_decision_promotes_engine_to_head() -> None:
    bus = FakeEventBus()
    debate = FakeCouncilDebate(
        decision_to_return=Decision(
            description="picked gemini",
            agent_engine=AgentEngineType.GEMINI_CLI,
            rationale="cheaper",
        ),
        arguments_to_return=[
            _arg(AgentEngineType.CODEX_CLI),
            _arg(AgentEngineType.CLAUDE_CODE),
        ],
    )
    council_uc = RunCouncilDebateUseCase(debate_port=debate, event_bus=bus)

    uc = RouteToEngineUseCase(
        drivers={},
        run_council_debate=council_uc,
        council_enabled=True,
    )
    chain = await uc._build_chain(
        task_type=TaskType.CODE_GENERATION,
        budget=1.0,
        estimated_hours=0.0,
        context_tokens=0,
        preferred_engine=None,
        topic="general",
        task="write a python function",
        task_id=None,
    )

    assert chain[0] is AgentEngineType.GEMINI_CLI
    assert chain[-1] is AgentEngineType.OLLAMA
    assert len(chain) == len(set(chain))
    for engine in _baseline_chain():
        assert engine in chain


@pytest.mark.asyncio
async def test_council_enabled_abandoned_chain_unchanged() -> None:
    bus = FakeEventBus()
    debate = FakeCouncilDebate(
        decision_to_return=Decision(
            description="unused",
            agent_engine=AgentEngineType.OLLAMA,
            rationale="unused",
        ),
        arguments_to_return=[
            _arg(AgentEngineType.CODEX_CLI),
            _arg(AgentEngineType.CLAUDE_CODE),
        ],
        raise_on_call=ValueError("boom"),
    )
    council_uc = RunCouncilDebateUseCase(debate_port=debate, event_bus=bus)

    uc = RouteToEngineUseCase(
        drivers={},
        run_council_debate=council_uc,
        council_enabled=True,
    )
    chain = await uc._build_chain(
        task_type=TaskType.CODE_GENERATION,
        budget=1.0,
        estimated_hours=0.0,
        context_tokens=0,
        preferred_engine=None,
        topic="general",
        task="write a python function",
        task_id=None,
    )
    assert chain == _baseline_chain()


class _StubTaskStateRepo:
    """Minimal in-memory SharedTaskStateRepository for FR-10 verification."""

    def __init__(self, initial: SharedTaskState | None = None) -> None:
        self._state = initial
        self.updated_decisions: list[Decision] = []

    async def get(self, task_id: str) -> SharedTaskState | None:
        return self._state

    async def update_decisions(self, state: SharedTaskState) -> None:
        self.updated_decisions = list(state.decisions)

    async def save(self, state: SharedTaskState) -> None: ...
    async def list_active(self) -> list[SharedTaskState]:
        return []
    async def update_artifacts(self, state: SharedTaskState) -> None: ...
    async def append_action(self, task_id, action) -> None: ...  # type: ignore[no-untyped-def]
    async def delete(self, task_id: str) -> None: ...


@pytest.mark.asyncio
async def test_record_council_decision_persists_via_port_methods() -> None:
    """FR-10: council Decision is appended to SharedTaskState via get + update_decisions.

    Regression for T-41: previously called a non-existent
    ``add_decision(task_id, decision)`` on the port — the call always
    raised AttributeError, was swallowed, and the decision was never
    persisted. Type-ignore was masking the bug.
    """
    state = SharedTaskState(task_id="t1")
    repo = _StubTaskStateRepo(initial=state)
    uc = RouteToEngineUseCase(drivers={}, task_state_repo=repo)

    decision = Decision(
        description="picked engine",
        agent_engine=AgentEngineType.GEMINI_CLI,
        rationale="cheapest",
    )
    await uc._record_council_decision(task_id="t1", decision=decision)

    assert len(repo.updated_decisions) == 1
    assert repo.updated_decisions[0].agent_engine is AgentEngineType.GEMINI_CLI


@pytest.mark.asyncio
async def test_record_council_decision_skips_when_state_missing() -> None:
    """When the SharedTaskState lookup returns None, no update is attempted."""
    repo = _StubTaskStateRepo(initial=None)
    uc = RouteToEngineUseCase(drivers={}, task_state_repo=repo)

    await uc._record_council_decision(
        task_id="missing",
        decision=Decision(
            description="x",
            agent_engine=AgentEngineType.OLLAMA,
            rationale="y",
        ),
    )
    assert repo.updated_decisions == []
