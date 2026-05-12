"""In-memory EventBusPort adapter — append-only recorder for the council pilot.

Spec: `specs/council-pilot/spec.md` (FR-7).
Plan: `specs/council-pilot/plan.md` §Infrastructure impls.
"""

from __future__ import annotations

from domain.entities.council import DebateEvent
from domain.ports.event_bus import EventBusPort


class InMemoryEventBus(EventBusPort):
    def __init__(self) -> None:
        self._events: list[DebateEvent] = []

    async def publish(self, event: DebateEvent) -> None:
        self._events.append(event)

    @property
    def events(self) -> list[DebateEvent]:
        return list(self._events)
