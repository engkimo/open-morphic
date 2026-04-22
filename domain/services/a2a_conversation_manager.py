"""A2AConversationManager — pure conversation lifecycle logic.

Creates conversations, validates messages, checks expiry.
No I/O — depends only on domain entities and value objects.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from domain.entities.a2a import A2AConversation, A2AMessage
from domain.value_objects.a2a import (
    A2AAction,
    A2AConversationStatus,
    A2AMessageType,
)
from domain.value_objects.agent_engine import AgentEngineType


class A2AConversationManager:
    """Pure domain service for A2A conversation lifecycle."""

    @staticmethod
    def create_conversation(
        task_id: str,
        participants: list[AgentEngineType],
        ttl_seconds: int = 300,
    ) -> A2AConversation:
        """Create a new open conversation."""
        return A2AConversation(
            id=str(uuid.uuid4()),
            task_id=task_id,
            participants=participants,
            status=A2AConversationStatus.OPEN,
            ttl_seconds=ttl_seconds,
        )

    @staticmethod
    def create_request(
        sender: AgentEngineType,
        receiver: AgentEngineType | None,
        conversation_id: str,
        task_id: str,
        action: A2AAction,
        payload: str,
        artifacts: dict[str, str] | None = None,
    ) -> A2AMessage:
        """Build a REQUEST message."""
        return A2AMessage(
            id=str(uuid.uuid4()),
            sender=sender,
            receiver=receiver,
            message_type=A2AMessageType.REQUEST,
            action=action,
            task_id=task_id,
            conversation_id=conversation_id,
            payload=payload,
            artifacts=artifacts or {},
        )

    @staticmethod
    def create_response(
        sender: AgentEngineType,
        request: A2AMessage,
        payload: str,
        artifacts: dict[str, str] | None = None,
    ) -> A2AMessage:
        """Build a RESPONSE message replying to *request*."""
        return A2AMessage(
            id=str(uuid.uuid4()),
            sender=sender,
            receiver=request.sender,
            message_type=A2AMessageType.RESPONSE,
            action=request.action,
            task_id=request.task_id,
            conversation_id=request.conversation_id,
            payload=payload,
            artifacts=artifacts or {},
            reply_to=request.id,
        )

    @staticmethod
    def is_expired(
        conversation: A2AConversation,
        now: datetime | None = None,
    ) -> bool:
        """Check whether the conversation has exceeded its TTL."""
        now = now or datetime.now()
        elapsed = (now - conversation.created_at).total_seconds()
        return elapsed > conversation.ttl_seconds

    @staticmethod
    def has_all_responses(
        conversation: A2AConversation,
    ) -> bool:
        """True if every participant (except the initial sender) has replied.

        Only considers the first request's sender as the initiator.
        """
        requests = [m for m in conversation.messages if m.message_type == A2AMessageType.REQUEST]
        if not requests:
            return False

        initiator = requests[0].sender
        expected = {p for p in conversation.participants if p != initiator}
        responded = {
            m.sender for m in conversation.messages if m.message_type == A2AMessageType.RESPONSE
        }
        return expected.issubset(responded)

    @staticmethod
    def pending_participants(
        conversation: A2AConversation,
    ) -> list[AgentEngineType]:
        """Return participants who haven't responded yet."""
        requests = [m for m in conversation.messages if m.message_type == A2AMessageType.REQUEST]
        if not requests:
            return list(conversation.participants)

        initiator = requests[0].sender
        responded = {
            m.sender for m in conversation.messages if m.message_type == A2AMessageType.RESPONSE
        }
        return [p for p in conversation.participants if p != initiator and p not in responded]
