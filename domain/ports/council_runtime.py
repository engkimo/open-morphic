"""Port for Morphic Chat CLI council deliberation."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.chat_session import ChatSession
from domain.entities.council_runtime import CouncilDecision, CouncilTurn
from domain.entities.workspace_context import ContextIndex
from domain.ports.agent_engine import AgentEngineEventSinkPort


class CouncilRuntimePort(ABC):
    """Runs role-based deliberation while keeping engines abstract."""

    @abstractmethod
    async def deliberate(
        self,
        session: ChatSession,
        context: ContextIndex,
        user_message: str,
    ) -> tuple[list[CouncilTurn], CouncilDecision]: ...


class StreamingCouncilRuntimePort(CouncilRuntimePort):
    """Council-compatible runtime that emits native events during execution."""

    @abstractmethod
    async def deliberate_stream(
        self,
        session: ChatSession,
        context: ContextIndex,
        user_message: str,
        event_sink: AgentEngineEventSinkPort,
    ) -> tuple[list[CouncilTurn], CouncilDecision]: ...
