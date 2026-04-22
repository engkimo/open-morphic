"""InMemoryA2ABroker — asyncio-based message broker for A2A protocol.

Suitable for single-process testing and local development.
Production would use Redis Streams or similar.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import defaultdict

from domain.entities.a2a import A2AMessage
from domain.ports.a2a_broker import A2AMessageBroker
from domain.value_objects.a2a import A2AMessageType
from domain.value_objects.agent_engine import AgentEngineType


class InMemoryA2ABroker(A2AMessageBroker):
    """In-memory message broker backed by asyncio.Queue per receiver."""

    def __init__(self) -> None:
        # Per-receiver inbox: engine -> Queue[A2AMessage]
        self._inboxes: dict[AgentEngineType, asyncio.Queue[A2AMessage]] = defaultdict(asyncio.Queue)
        # All messages indexed by conversation_id for poll_replies
        self._by_conversation: dict[str, list[A2AMessage]] = defaultdict(list)
        # Event fired whenever a message arrives for a conversation
        self._conversation_events: dict[str, asyncio.Event] = defaultdict(asyncio.Event)

    async def send(self, message: A2AMessage) -> str:
        """Deliver a message to the receiver's inbox (or all inboxes if broadcast)."""
        self._by_conversation[message.conversation_id].append(message)
        self._conversation_events[message.conversation_id].set()

        if message.is_broadcast:
            # Deliver to all known inboxes
            for queue in self._inboxes.values():
                await queue.put(message)
        else:
            assert message.receiver is not None
            await self._inboxes[message.receiver].put(message)

        return message.id

    async def receive(
        self,
        receiver: AgentEngineType,
        timeout: float = 10.0,
    ) -> A2AMessage | None:
        """Wait for the next message addressed to *receiver*."""
        queue = self._inboxes[receiver]
        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        except TimeoutError:
            return None

    async def poll_replies(
        self,
        conversation_id: str,
        timeout: float = 10.0,
    ) -> list[A2AMessage]:
        """Collect all reply messages for a conversation within *timeout*."""
        event = self._conversation_events[conversation_id]

        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(event.wait(), timeout=timeout)

        # Return only RESPONSE messages for this conversation
        return [
            m
            for m in self._by_conversation.get(conversation_id, [])
            if m.message_type == A2AMessageType.RESPONSE
        ]
