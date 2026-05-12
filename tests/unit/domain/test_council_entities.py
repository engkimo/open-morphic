"""Council entity tests — RED gate for domain/entities/council.py.

Per specs/council-pilot/tasks.md T-05.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.entities.cognitive import Decision
from domain.entities.council import Argument, SubtaskBrief
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.council_events import DebateStarted, DecisionResolved
from domain.value_objects.model_tier import TaskType


def _make_argument() -> Argument:
    return Argument(
        engine=AgentEngineType.OLLAMA,
        capability_claim="local-first, fast for short prompts",
        cost_claim="$0 per call",
        risk_claim="lower quality on multi-step reasoning",
        recommended_approach="single-shot completion",
    )


def test_argument_round_trip() -> None:
    original = _make_argument()
    rebuilt = Argument.model_validate_json(original.model_dump_json())
    assert rebuilt == original


def test_subtask_brief_required_fields() -> None:
    with pytest.raises(ValidationError):
        SubtaskBrief(id="task-1", description="", task_type=TaskType.SIMPLE_QA)


def test_debate_event_discriminator() -> None:
    decision = Decision(
        description="Use Ollama for this short answer",
        agent_engine=AgentEngineType.OLLAMA,
        rationale="cheapest path",
    )
    arguments = [_make_argument(), _make_argument()]
    resolved = DecisionResolved(decision=decision, arguments=arguments)
    payload = resolved.model_dump_json()

    from domain.value_objects.council_events import DebateEventAdapter

    parsed = DebateEventAdapter.validate_json(payload)
    assert isinstance(parsed, DecisionResolved)
    assert parsed.decision.agent_engine is AgentEngineType.OLLAMA


def test_debate_started_minimal() -> None:
    brief = SubtaskBrief(
        id="task-1", description="Answer 2+2", task_type=TaskType.SIMPLE_QA
    )
    event = DebateStarted(
        subtask=brief,
        candidates=[AgentEngineType.OLLAMA, AgentEngineType.GEMINI_CLI],
    )
    assert event.kind == "debate_started"
    assert event.debate_id  # autogen
    assert event.started_at is not None
