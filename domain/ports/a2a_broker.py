"""A2AMessageBroker — port for async agent-to-agent message passing.

Infrastructure implementations may use Redis Streams, RabbitMQ,
or an in-memory queue for testing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.a2a import A2AMessage
from domain.value_objects.agent_engine import AgentEngineType


class A2AMessageBroker(ABC):
    """Abstract broker for A2A message delivery."""

    @abstractmethod
    async def send(self, message: A2AMessage) -> str:
        """Send a message. Returns the message id."""
        ...

    @abstractmethod
    async def receive(
        self,
        receiver: AgentEngineType,
        timeout: float = 10.0,
    ) -> A2AMessage | None:
        """Wait for the next message addressed to *receiver*.

        Returns ``None`` on timeout.
        """
        ...

    @abstractmethod
    async def poll_replies(
        self,
        conversation_id: str,
        timeout: float = 10.0,
    ) -> list[A2AMessage]:
        """Collect all reply messages for a conversation within *timeout*."""
        ...
