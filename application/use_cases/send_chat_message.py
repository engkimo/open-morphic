"""SendChatMessageUseCase — append user turn and council response events."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from domain.entities.agent_engine_event import AgentEngineEvent
from domain.entities.chat_event import ChatEvent, ChatEventType
from domain.entities.chat_session import ChatSession
from domain.entities.workspace_context import ContextIndex
from domain.ports.agent_engine import AgentEngineEventSinkPort
from domain.ports.chat_session_store import ChatSessionStorePort
from domain.ports.council_runtime import CouncilRuntimePort, StreamingCouncilRuntimePort

logger = logging.getLogger(__name__)


class _LedgerEngineEventSink(AgentEngineEventSinkPort):
    def __init__(
        self,
        *,
        session: ChatSession,
        events: list[ChatEvent],
        session_store: ChatSessionStorePort,
        observer: AgentEngineEventSinkPort | None = None,
    ) -> None:
        self.session = session
        self._events = events
        self._session_store = session_store
        self._observer = observer

    async def publish(self, engine_event: AgentEngineEvent) -> None:
        self.session, event = self.session.record_event(
            ChatEventType.ENGINE_EVENT,
            engine_event.model_dump(mode="json"),
        )
        self._events.append(event)
        await self._session_store.append_event(event)
        if self._observer is not None:
            try:
                await self._observer.publish(engine_event)
            except Exception:
                logger.warning("Native engine progress observer failed", exc_info=True)


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
        engine_event_observer: AgentEngineEventSinkPort | None = None,
    ) -> None:
        self._session_store = session_store
        self._council_runtime = council_runtime
        self._engine_event_observer = engine_event_observer

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
        streaming = isinstance(self._council_runtime, StreamingCouncilRuntimePort)
        persisted_count = 0
        if streaming:
            await self._session_store.append_event(user_event)
            persisted_count = 1
            sink = _LedgerEngineEventSink(
                session=current,
                events=events,
                session_store=self._session_store,
                observer=self._engine_event_observer,
            )
            turns, decision = await self._council_runtime.deliberate_stream(
                current,
                context,
                message,
                sink,
            )
            current = sink.session
            persisted_count = len(events)
        else:
            turns, decision = await self._council_runtime.deliberate(
                current,
                context,
                message,
            )

        for turn in turns:
            if not streaming:
                for engine_event in turn.engine_events:
                    current, event = current.record_event(
                        ChatEventType.ENGINE_EVENT,
                        engine_event.model_dump(mode="json"),
                    )
                    events.append(event)
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

        for event in events[persisted_count:]:
            await self._session_store.append_event(event)

        return SendChatMessageResult(session=current, events=events)
