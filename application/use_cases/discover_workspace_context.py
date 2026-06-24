"""DiscoverWorkspaceContextUseCase — index workspace context sources."""

from __future__ import annotations

from dataclasses import dataclass

from domain.entities.chat_event import ChatEvent, ChatEventType
from domain.entities.chat_session import ChatSession
from domain.entities.workspace_context import ContextIndex
from domain.ports.chat_session_store import ChatSessionStorePort
from domain.ports.context_discovery import ContextDiscoveryPort


@dataclass(frozen=True)
class DiscoverWorkspaceContextResult:
    index: ContextIndex
    session: ChatSession | None = None
    event: ChatEvent | None = None


class DiscoverWorkspaceContextUseCase:
    def __init__(
        self,
        *,
        context_discovery: ContextDiscoveryPort,
        session_store: ChatSessionStorePort | None = None,
    ) -> None:
        self._context_discovery = context_discovery
        self._session_store = session_store

    async def execute(
        self,
        *,
        workspace_root: str,
        session: ChatSession | None = None,
    ) -> DiscoverWorkspaceContextResult:
        index = await self._context_discovery.discover(workspace_root)
        if session is None:
            return DiscoverWorkspaceContextResult(index=index)

        updated, event = session.record_event(
            ChatEventType.CONTEXT_INDEXED,
            {
                "workspace_root": index.workspace_root,
                "source_count": len(index.sources),
                "sources": [
                    {
                        "source_path": source.source_path,
                        "source_type": source.source_type.value,
                        "precedence": source.precedence,
                    }
                    for source in index.sources
                ],
            },
        )
        if self._session_store is not None:
            await self._session_store.append_event(event)
        return DiscoverWorkspaceContextResult(index=index, session=updated, event=event)
