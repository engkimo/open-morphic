"""RunCouncilDebateUseCase — orchestrates a single debate + event emission.

Spec: `specs/council-pilot/spec.md` (FR-1, FR-2, FR-3, FR-7, FR-11).
Plan: `specs/council-pilot/plan.md` §Use cases added.

The use case is responsible for emitting the four debate events; the
`CouncilDebatePort` stays a pure deliberation function.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from domain.entities.cognitive import Decision
from domain.entities.council import SubtaskBrief
from domain.ports.council_debate import CouncilDebatePort
from domain.ports.event_bus import EventBusPort
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.council_events import (
    ArgumentSubmitted,
    DebateAbandoned,
    DebateStarted,
    DecisionResolved,
)

logger = logging.getLogger(__name__)


class RunCouncilDebateUseCase:
    def __init__(
        self,
        *,
        debate_port: CouncilDebatePort,
        event_bus: EventBusPort,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._debate_port = debate_port
        self._event_bus = event_bus
        self._timeout_seconds = timeout_seconds

    async def execute(
        self,
        subtask: SubtaskBrief,
        candidates: list[AgentEngineType],
    ) -> Decision | None:
        if len(candidates) != 2:
            raise ValueError(
                f"council debate requires exactly 2 candidates, got {len(candidates)}"
            )

        debate_id = str(uuid.uuid4())
        await self._event_bus.publish(
            DebateStarted(
                debate_id=debate_id,
                subtask=subtask,
                candidates=list(candidates),
            )
        )

        try:
            decision, arguments = await asyncio.wait_for(
                self._debate_port.debate(subtask, candidates),
                timeout=self._timeout_seconds,
            )
        except TimeoutError:
            await self._event_bus.publish(
                DebateAbandoned(debate_id=debate_id, reason="timeout")
            )
            logger.warning("council debate %s timed out", debate_id)
            return None
        except Exception as exc:  # noqa: BLE001 — funnel any debate failure to abandonment
            await self._event_bus.publish(
                DebateAbandoned(debate_id=debate_id, reason=f"error: {exc}")
            )
            logger.warning("council debate %s aborted: %s", debate_id, exc)
            return None

        for argument in arguments:
            await self._event_bus.publish(
                ArgumentSubmitted(debate_id=debate_id, argument=argument)
            )
        await self._event_bus.publish(
            DecisionResolved(
                debate_id=debate_id,
                decision=decision,
                arguments=list(arguments),
            )
        )
        return decision
