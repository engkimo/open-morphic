"""SendA2AMessage — orchestrates sending a message between agents.

Uses the A2ARouter for receiver selection, A2AConversationManager for
message construction, and A2AMessageBroker for delivery.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.entities.a2a import A2AConversation, A2AMessage
from domain.ports.a2a_broker import A2AMessageBroker
from domain.ports.agent_registry import AgentRegistryPort
from domain.services.a2a_conversation_manager import A2AConversationManager
from domain.services.a2a_router import A2ARouter
from domain.value_objects.a2a import A2AAction
from domain.value_objects.agent_engine import AgentEngineType


@dataclass
class SendResult:
    """Result of sending an A2A message."""

    message_id: str
    conversation_id: str
    receiver: AgentEngineType | None
    routed: bool  # True if receiver was auto-selected by router


class SendA2AMessageUseCase:
    """Send a message from one agent to another (or broadcast).

    If no receiver is specified, uses A2ARouter to find the best candidate.
    """

    def __init__(
        self,
        broker: A2AMessageBroker,
        registry: AgentRegistryPort,
    ) -> None:
        self._broker = broker
        self._registry = registry

    async def execute(
        self,
        sender: AgentEngineType,
        action: A2AAction,
        conversation: A2AConversation,
        payload: str,
        receiver: AgentEngineType | None = None,
        artifacts: dict[str, str] | None = None,
    ) -> SendResult:
        """Send a REQUEST message in the given conversation.

        If *receiver* is None, auto-routes via capability + affinity scoring.
        """
        routed = False

        if receiver is None:
            receiver = await self._route(action, sender)
            routed = receiver is not None

        msg = A2AConversationManager.create_request(
            sender=sender,
            receiver=receiver,
            conversation_id=conversation.id,
            task_id=conversation.task_id,
            action=action,
            payload=payload,
            artifacts=artifacts,
        )

        conversation.add_message(msg)
        msg_id = await self._broker.send(msg)

        return SendResult(
            message_id=msg_id,
            conversation_id=conversation.id,
            receiver=receiver,
            routed=routed,
        )

    async def reply(
        self,
        sender: AgentEngineType,
        request: A2AMessage,
        conversation: A2AConversation,
        payload: str,
        artifacts: dict[str, str] | None = None,
    ) -> SendResult:
        """Send a RESPONSE message replying to a specific request."""
        resp = A2AConversationManager.create_response(
            sender=sender,
            request=request,
            payload=payload,
            artifacts=artifacts,
        )

        conversation.add_message(resp)
        msg_id = await self._broker.send(resp)

        return SendResult(
            message_id=msg_id,
            conversation_id=conversation.id,
            receiver=request.sender,
            routed=False,
        )

    async def _route(
        self,
        action: A2AAction,
        exclude: AgentEngineType,
    ) -> AgentEngineType | None:
        """Use router + registry to find the best receiver."""
        available = await self._registry.list_available()
        if not available:
            return None
        return A2ARouter.select_receiver(action, available, exclude=exclude)
