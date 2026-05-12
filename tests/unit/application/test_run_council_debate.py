"""RunCouncilDebateUseCase tests — RED gate per tasks T-13."""

from __future__ import annotations

import pytest

from domain.entities.cognitive import Decision
from domain.entities.council import (
    Argument,
    ArgumentSubmitted,
    DebateAbandoned,
    DebateStarted,
    DecisionResolved,
    SubtaskBrief,
)
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


def _brief() -> SubtaskBrief:
    return SubtaskBrief(id="t1", description="do thing", task_type=TaskType.SIMPLE_QA)


def _decision(engine: AgentEngineType) -> Decision:
    return Decision(
        description="picked engine",
        agent_engine=engine,
        rationale="why",
    )


@pytest.mark.asyncio
async def test_happy_path_emits_four_events_in_order() -> None:
    from application.use_cases.run_council_debate import RunCouncilDebateUseCase

    bus = FakeEventBus()
    debate = FakeCouncilDebate(
        decision_to_return=_decision(AgentEngineType.OLLAMA),
        arguments_to_return=[_arg(AgentEngineType.OLLAMA), _arg(AgentEngineType.GEMINI_CLI)],
    )
    uc = RunCouncilDebateUseCase(debate_port=debate, event_bus=bus)

    result = await uc.execute(
        _brief(), [AgentEngineType.OLLAMA, AgentEngineType.GEMINI_CLI]
    )

    assert result is not None
    assert result.agent_engine is AgentEngineType.OLLAMA
    kinds = [e.kind for e in bus.events]
    assert kinds == [
        "debate_started",
        "argument_submitted",
        "argument_submitted",
        "decision_resolved",
    ]
    assert isinstance(bus.events[0], DebateStarted)
    assert isinstance(bus.events[1], ArgumentSubmitted)
    assert isinstance(bus.events[3], DecisionResolved)
    debate_id = bus.events[0].debate_id
    assert all(e.debate_id == debate_id for e in bus.events)


@pytest.mark.asyncio
async def test_timeout_emits_debate_abandoned() -> None:
    from application.use_cases.run_council_debate import RunCouncilDebateUseCase

    bus = FakeEventBus()
    debate = FakeCouncilDebate(
        decision_to_return=_decision(AgentEngineType.OLLAMA),
        arguments_to_return=[_arg(AgentEngineType.OLLAMA), _arg(AgentEngineType.GEMINI_CLI)],
        delay_seconds=2.0,
    )
    uc = RunCouncilDebateUseCase(debate_port=debate, event_bus=bus, timeout_seconds=0.05)

    result = await uc.execute(
        _brief(), [AgentEngineType.OLLAMA, AgentEngineType.GEMINI_CLI]
    )

    assert result is None
    assert bus.events[-1].kind == "debate_abandoned"
    abandoned = bus.events[-1]
    assert isinstance(abandoned, DebateAbandoned)
    assert abandoned.reason == "timeout"


@pytest.mark.asyncio
async def test_exception_emits_debate_abandoned() -> None:
    from application.use_cases.run_council_debate import RunCouncilDebateUseCase

    bus = FakeEventBus()
    debate = FakeCouncilDebate(
        decision_to_return=_decision(AgentEngineType.OLLAMA),
        arguments_to_return=[_arg(AgentEngineType.OLLAMA), _arg(AgentEngineType.GEMINI_CLI)],
        raise_on_call=ValueError("boom"),
    )
    uc = RunCouncilDebateUseCase(debate_port=debate, event_bus=bus)

    result = await uc.execute(
        _brief(), [AgentEngineType.OLLAMA, AgentEngineType.GEMINI_CLI]
    )

    assert result is None
    assert bus.events[-1].kind == "debate_abandoned"
    abandoned = bus.events[-1]
    assert isinstance(abandoned, DebateAbandoned)
    assert "boom" in abandoned.reason or abandoned.reason


@pytest.mark.asyncio
async def test_validation_two_candidates_required() -> None:
    from application.use_cases.run_council_debate import RunCouncilDebateUseCase

    bus = FakeEventBus()
    debate = FakeCouncilDebate(
        decision_to_return=_decision(AgentEngineType.OLLAMA),
        arguments_to_return=[_arg(AgentEngineType.OLLAMA)],
    )
    uc = RunCouncilDebateUseCase(debate_port=debate, event_bus=bus)

    with pytest.raises(ValueError):
        await uc.execute(_brief(), [AgentEngineType.OLLAMA])

    assert bus.events == []
