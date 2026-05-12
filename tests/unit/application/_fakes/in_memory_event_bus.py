"""In-memory EventBusPort fake for unit tests.

Per TD-187, test code MAY import port-compliant `InMemory*` adapters from
`infrastructure/`, but for the council pilot the unit tests use this
test-local fake to stay decoupled from the production adapter (which may
grow features the unit tests do not care about).
"""

from __future__ import annotations

from domain.entities.council import DebateEvent
from domain.ports.event_bus import EventBusPort


class FakeEventBus(EventBusPort):
    def __init__(self) -> None:
        self.events: list[DebateEvent] = []

    async def publish(self, event: DebateEvent) -> None:
        self.events.append(event)
