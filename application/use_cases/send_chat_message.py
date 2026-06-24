"""SendChatMessageUseCase — append user turn and council response events."""

from __future__ import annotations

from dataclasses import dataclass

from domain.entities.chat_event import ChatEvent, ChatEventType
from domain.entities.chat_session import ChatSession
from domain.entities.workspace_context import ContextIndex
from domain.ports.chat_session_store import ChatSessionStorePort
from domain.ports.council_runtime import CouncilRuntimePort


@dataclass(frozen=True)
class SendChatMessageResult:
    session: ChatSession
    events: list[ChatEvent]


class SendChatMessageUseCase:
    def __init__(
        self,
        *,
        session_store: ChatSessionStorePort,
        council_runtime: CouncilRuntimePort,
    ) -> None:
        self._session_store = session_store
        self._council_runtime = council_runtime

    async def execute(
        self,
        *,
        session: ChatSession,
        context: ContextIndex,
        message: str,
    ) -> SendChatMessageResult:
        if not message.strip():
            raise ValueError("chat message must not be empty")

        current, user_event = session.record_event(
            ChatEventType.USER_MESSAGE,
            {"text": message},
        )
        events = [user_event]

        turns, decision = await self._council_runtime.deliberate(
            current,
            context,
            message,
        )

        for turn in turns:
            current, event = current.record_event(
                ChatEventType.COUNCIL_ARGUMENT,
                turn.model_dump(mode="json"),
            )
            events.append(event)

        current, decision_event = current.record_event(
            ChatEventType.COUNCIL_DECISION,
            decision.model_dump(mode="json"),
        )
        events.append(decision_event)

        current, assistant_event = current.record_event(
            ChatEventType.ASSISTANT_MESSAGE,
            {
                "text": decision.selected_content,
                "role": decision.selected_role.value,
                "leader_engine_id": decision.leader_engine_id,
            },
        )
        events.append(assistant_event)

        for event in events:
            await self._session_store.append_event(event)

        return SendChatMessageResult(session=current, events=events)
