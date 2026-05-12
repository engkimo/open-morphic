"""EventBusPort — publish-only domain event bus.

Spec: `specs/council-pilot/spec.md` (FR-7).
Plan: `specs/council-pilot/plan.md` §Ports added.

The subscribe / consume side is intentionally absent in this spike. The
next sprint will introduce a transport-bound subscriber (SSE / WebSocket);
until then the in-memory recording adapter in ``infrastructure/events/``
is the only consumer (test-only).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.council import DebateEvent


class EventBusPort(ABC):
    """Publish-only contract for council debate events."""

    @abstractmethod
    async def publish(self, event: DebateEvent) -> None: ...
