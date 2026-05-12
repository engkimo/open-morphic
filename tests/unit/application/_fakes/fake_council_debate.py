"""Configurable fake CouncilDebatePort for unit tests."""

from __future__ import annotations

import asyncio

from domain.entities.cognitive import Decision
from domain.entities.council import Argument, SubtaskBrief
from domain.ports.council_debate import CouncilDebatePort
from domain.value_objects.agent_engine import AgentEngineType


class FakeCouncilDebate(CouncilDebatePort):
    def __init__(
        self,
        *,
        decision_to_return: Decision,
        arguments_to_return: list[Argument],
        raise_on_call: Exception | None = None,
        delay_seconds: float = 0.0,
    ) -> None:
        self.decision_to_return = decision_to_return
        self.arguments_to_return = arguments_to_return
        self.raise_on_call = raise_on_call
        self.delay_seconds = delay_seconds
        self.calls: list[tuple[SubtaskBrief, list[AgentEngineType]]] = []

    async def debate(
        self,
        subtask: SubtaskBrief,
        candidates: list[AgentEngineType],
    ) -> tuple[Decision, list[Argument]]:
        self.calls.append((subtask, list(candidates)))
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.raise_on_call is not None:
            raise self.raise_on_call
        return self.decision_to_return, list(self.arguments_to_return)
