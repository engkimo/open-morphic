"""A2A (Agent-to-Agent) Protocol entities.

A2AMessage — a single message between agents (request, response, broadcast).
A2AConversation — a multi-turn session linking messages and SharedTaskState.
AgentDescriptor — self-description of an agent for registry / discovery.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from domain.value_objects.a2a import (
    A2AAction,
    A2AConversationStatus,
    A2AMessageType,
)
from domain.value_objects.agent_engine import AgentEngineType


class A2AMessage(BaseModel):
    """A single message in the A2A protocol."""

    model_config = ConfigDict(strict=True, validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender: AgentEngineType
    receiver: AgentEngineType | None = None  # None = broadcast
    message_type: A2AMessageType
    action: A2AAction
    task_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    payload: str = ""  # task description or result text
    artifacts: dict[str, str] = Field(default_factory=dict)
    context_summary: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)
    reply_to: str | None = None  # message id this replies to

    @property
    def is_broadcast(self) -> bool:
        return self.receiver is None


class A2AConversation(BaseModel):
    """A multi-turn A2A conversation session.

    Links messages together and tracks participants and lifecycle.
    Tied to a SharedTaskState via task_id.
    """

    model_config = ConfigDict(strict=True, validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = Field(min_length=1)
    participants: list[AgentEngineType] = Field(min_length=1)
    messages: list[A2AMessage] = Field(default_factory=list)
    status: A2AConversationStatus = A2AConversationStatus.OPEN
    created_at: datetime = Field(default_factory=datetime.now)
    resolved_at: datetime | None = None
    ttl_seconds: int = Field(default=300, ge=1)

    def add_message(self, message: A2AMessage) -> None:
        """Append a message to the conversation."""
        self.messages.append(message)

    def resolve(self) -> None:
        """Mark the conversation as resolved."""
        self.status = A2AConversationStatus.RESOLVED
        self.resolved_at = datetime.now()

    def mark_error(self) -> None:
        """Mark the conversation as errored."""
        self.status = A2AConversationStatus.ERROR

    def mark_timeout(self) -> None:
        """Mark the conversation as timed out."""
        self.status = A2AConversationStatus.TIMEOUT

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def last_message(self) -> A2AMessage | None:
        return self.messages[-1] if self.messages else None

    @property
    def is_open(self) -> bool:
        return self.status == A2AConversationStatus.OPEN

    def get_messages_by_sender(self, sender: AgentEngineType) -> list[A2AMessage]:
        """Filter messages from a specific sender."""
        return [m for m in self.messages if m.sender == sender]

    def get_responses(self) -> list[A2AMessage]:
        """All response-type messages in this conversation."""
        return [m for m in self.messages if m.message_type == A2AMessageType.RESPONSE]


class AgentDescriptor(BaseModel):
    """Self-description of an agent for registry and discovery.

    Allows agents to advertise capabilities so the router can
    find the right agent for a given action.
    """

    model_config = ConfigDict(strict=True, validate_assignment=True)

    agent_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    engine_type: AgentEngineType
    capabilities: list[str] = Field(default_factory=list)
    status: str = Field(default="available", min_length=1)
    last_seen: datetime = Field(default_factory=datetime.now)

    def update_heartbeat(self) -> None:
        """Update last_seen to now."""
        self.last_seen = datetime.now()

    def has_capability(self, capability: str) -> bool:
        """Check if this agent advertises a given capability."""
        lower = capability.lower()
        return any(c.lower() == lower for c in self.capabilities)
