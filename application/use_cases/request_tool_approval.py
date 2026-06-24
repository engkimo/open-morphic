"""RequestToolApprovalUseCase — record a pending user approval."""

from __future__ import annotations

from dataclasses import dataclass

from domain.entities.approval import ApprovalRequest
from domain.entities.chat_event import ChatEvent, ChatEventType
from domain.entities.chat_session import ChatSession, ChatSessionStatus
from domain.ports.chat_session_store import ChatSessionStorePort
from domain.value_objects import RiskLevel


@dataclass(frozen=True)
class RequestToolApprovalResult:
    session: ChatSession
    request: ApprovalRequest
    event: ChatEvent


class RequestToolApprovalUseCase:
    def __init__(self, *, session_store: ChatSessionStorePort) -> None:
        self._session_store = session_store

    async def execute(
        self,
        *,
        session: ChatSession,
        action_summary: str,
        risk_level: RiskLevel,
        reason: str,
    ) -> RequestToolApprovalResult:
        request = ApprovalRequest(
            session_id=session.id,
            action_summary=action_summary,
            risk_level=risk_level,
            reason=reason,
        )
        updated = session.model_copy(
            update={"status": ChatSessionStatus.WAITING_FOR_APPROVAL}
        )
        updated, event = updated.record_event(
            ChatEventType.APPROVAL_REQUESTED,
            request.model_dump(mode="json"),
        )
        await self._session_store.append_event(event)
        return RequestToolApprovalResult(
            session=updated,
            request=request,
            event=event,
        )
