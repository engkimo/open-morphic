"""CouncilDebatePort — two-engine deliberation over a subtask.

Spec: `specs/council-pilot/spec.md` (FR-1, FR-2, FR-3, FR-12).
Plan: `specs/council-pilot/plan.md` §Ports added.

The application layer is responsible for emitting events; the port stays a
pure deliberation function that returns the resolved `Decision` together
with the two `Argument`s that produced it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.cognitive import Decision
from domain.entities.council import Argument, SubtaskBrief
from domain.value_objects.agent_engine import AgentEngineType


class CouncilDebatePort(ABC):
    """Two-engine debate over a subtask.

    Single-debate assumption: each call is independent (no cross-debate
    memory in this spike). Implementations MUST validate that
    ``len(candidates) == 2`` and raise ``ValueError`` otherwise — the
    spike scope is intentionally pinned to the cheapest 2-engine pair
    (FR-12).
    """

    @abstractmethod
    async def debate(
        self,
        subtask: SubtaskBrief,
        candidates: list[AgentEngineType],
    ) -> tuple[Decision, list[Argument]]: ...
