"""ManageA2AConversation — conversation lifecycle use case.

Creates, monitors, and finalizes A2A conversations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from domain.entities.a2a import A2AConversation
from domain.ports.a2a_broker import A2AMessageBroker
from domain.services.a2a_conversation_manager import A2AConversationManager
from domain.value_objects.a2a import A2AConversationStatus
from domain.value_objects.agent_engine import AgentEngineType


@dataclass
class ConversationSummary:
    """Summary of a completed conversation."""

    conversation_id: str
    task_id: str
    status: A2AConversationStatus
    message_count: int
    response_count: int
    pending_count: int


class ManageA2AConversationUseCase:
    """Manage the lifecycle of an A2A conversation."""

    def __init__(self, broker: A2AMessageBroker) -> None:
        self._broker = broker

    def create(
        self,
        task_id: str,
        participants: list[AgentEngineType],
        ttl_seconds: int = 300,
    ) -> A2AConversation:
        """Create a new conversation."""
        return A2AConversationManager.create_conversation(
            task_id=task_id,
            participants=participants,
            ttl_seconds=ttl_seconds,
        )

    def check_expired(
        self,
        conversation: A2AConversation,
        now: datetime | None = None,
    ) -> bool:
        """Check if the conversation has expired and mark it if so."""
        if not conversation.is_open:
            return False
        if A2AConversationManager.is_expired(conversation, now=now):
            conversation.mark_timeout()
            return True
        return False

    def check_complete(
        self,
        conversation: A2AConversation,
    ) -> bool:
        """Check if all participants have responded and resolve if so."""
        if not conversation.is_open:
            return False
        if A2AConversationManager.has_all_responses(conversation):
            conversation.resolve()
            return True
        return False

    async def collect_replies(
        self,
        conversation: A2AConversation,
        timeout: float = 10.0,
    ) -> int:
        """Poll for replies and add them to the conversation.

        Returns the number of new replies collected.
        """
        replies = await self._broker.poll_replies(conversation.id, timeout=timeout)
        new_count = 0
        existing_ids = {m.id for m in conversation.messages}
        for reply in replies:
            if reply.id not in existing_ids:
                conversation.add_message(reply)
                new_count += 1
        return new_count

    def summarize(self, conversation: A2AConversation) -> ConversationSummary:
        """Generate a summary of the conversation state."""
        pending = A2AConversationManager.pending_participants(conversation)
        return ConversationSummary(
            conversation_id=conversation.id,
            task_id=conversation.task_id,
            status=conversation.status,
            message_count=conversation.message_count,
            response_count=len(conversation.get_responses()),
            pending_count=len(pending),
        )
