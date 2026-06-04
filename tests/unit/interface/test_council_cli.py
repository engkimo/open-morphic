"""CLI tests for `morphic council debate` (TD-194 surface)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from typer.testing import CliRunner

from domain.entities.cognitive import Decision
from domain.entities.council import Argument, SubtaskBrief
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.council_events import (
    ArgumentSubmitted,
    DebateStarted,
    DecisionResolved,
)
from domain.value_objects.model_tier import TaskType
from interface.cli import _utils as cli_utils
from interface.cli.main import app

runner = CliRunner()


def _arg(engine: AgentEngineType) -> Argument:
    return Argument(
        engine=engine,
        capability_claim="cap",
        cost_claim="cost",
        risk_claim="risk",
        recommended_approach="approach",
    )


def _make_container(decision: Decision | None, events: list) -> SimpleNamespace:
    run_council = SimpleNamespace(execute=AsyncMock(return_value=decision))
    return SimpleNamespace(
        run_council_debate=run_council,
        council_event_bus=SimpleNamespace(events=events),
    )


def test_council_debate_prints_verdict() -> None:
    decision = Decision(
        description="x",
        rationale="claude_code is more decisive for this task",
        agent_engine=AgentEngineType.CLAUDE_CODE,
    )
    args = [_arg(AgentEngineType.OLLAMA), _arg(AgentEngineType.CLAUDE_CODE)]
    events = [
        DebateStarted(
            subtask=SubtaskBrief(id="s", description="g", task_type=TaskType.SIMPLE_QA),
            candidates=[AgentEngineType.OLLAMA, AgentEngineType.CLAUDE_CODE],
        ),
        ArgumentSubmitted(argument=args[0]),
        ArgumentSubmitted(argument=args[1]),
        DecisionResolved(decision=decision, arguments=args),
    ]
    cli_utils._set_container(_make_container(decision, events))
    try:
        result = runner.invoke(app, ["council", "debate", "Python or Go for an MVP?"])
    finally:
        cli_utils._set_container(None)

    assert result.exit_code == 0, result.output
    assert "claude_code" in result.output
    assert "Verdict" in result.output


def test_council_debate_abandoned_shows_reason() -> None:
    from domain.value_objects.council_events import DebateAbandoned

    events = [DebateAbandoned(reason="resolver model unavailable: bad key")]
    cli_utils._set_container(_make_container(None, events))
    try:
        result = runner.invoke(app, ["council", "debate", "x"])
    finally:
        cli_utils._set_container(None)

    assert result.exit_code == 0, result.output
    assert "abandoned" in result.output.lower()
    assert "resolver model unavailable" in result.output


def test_council_debate_rejects_wrong_engine_count() -> None:
    cli_utils._set_container(_make_container(None, []))
    try:
        result = runner.invoke(app, ["council", "debate", "x", "--engines", "ollama"])
    finally:
        cli_utils._set_container(None)
    assert result.exit_code == 1


def test_council_debate_rejects_unknown_engine() -> None:
    cli_utils._set_container(_make_container(None, []))
    try:
        result = runner.invoke(
            app, ["council", "debate", "x", "--engines", "ollama,nope"]
        )
    finally:
        cli_utils._set_container(None)
    assert result.exit_code == 1
