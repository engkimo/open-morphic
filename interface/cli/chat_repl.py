"""Line-oriented REPL for Morphic Chat CLI."""

from __future__ import annotations

import uuid
from pathlib import Path

from application.use_cases.discover_workspace_context import DiscoverWorkspaceContextUseCase
from application.use_cases.execute_slash_command import ExecuteSlashCommandUseCase
from application.use_cases.resume_chat_session import ResumeChatSessionUseCase
from application.use_cases.send_chat_message import SendChatMessageUseCase
from application.use_cases.start_chat_session import StartChatSessionUseCase
from domain.entities.chat_session import ChatSession, PermissionMode
from domain.entities.workspace_context import ContextIndex
from infrastructure.chat.jsonl_session_store import JsonlChatSessionStore
from infrastructure.context.workspace_context_discovery import WorkspaceContextDiscovery
from infrastructure.council.local_chat_council_runtime import LocalChatCouncilRuntime
from infrastructure.engines.static_engine_registry import StaticEngineRegistry
from interface.cli.formatters import console


class ChatRepl:
    """Portable line-oriented chat loop."""

    def __init__(self, *, workspace_root: Path) -> None:
        self._workspace_root = workspace_root
        self._session_store = JsonlChatSessionStore(workspace_root=workspace_root)
        self._context_discovery = WorkspaceContextDiscovery()
        self._council_runtime = LocalChatCouncilRuntime()
        self._engine_registry = StaticEngineRegistry()

    async def run(
        self,
        *,
        resume: str | None = None,
        permission_mode: PermissionMode = PermissionMode.CONFIRM_DESTRUCTIVE,
    ) -> ChatSession:
        session = await self._load_or_start_session(
            resume=resume,
            permission_mode=permission_mode,
            goal=None,
        )
        session, context = await self._discover_context(session)
        console.print(f"Morphic chat session {session.id}")

        while True:
            try:
                line = input("> ")
            except EOFError:
                break
            if not line.strip():
                continue
            if line.strip().startswith("/"):
                result = await ExecuteSlashCommandUseCase(
                    session_store=self._session_store,
                    engine_registry=self._engine_registry,
                ).execute(session=session, command=line, context=context)
                session = result.session
                console.print(result.output)
                if result.should_exit:
                    break
                continue

            result = await SendChatMessageUseCase(
                session_store=self._session_store,
                council_runtime=self._council_runtime,
            ).execute(session=session, context=context, message=line)
            session = result.session
            console.print(result.events[-1].payload["text"])

        return session

    async def run_goal(
        self,
        *,
        goal: str,
        permission_mode: PermissionMode = PermissionMode.CONFIRM_DESTRUCTIVE,
    ) -> str:
        session = await self._load_or_start_session(
            resume=None,
            permission_mode=permission_mode,
            goal=goal,
        )
        session, context = await self._discover_context(session)
        result = await SendChatMessageUseCase(
            session_store=self._session_store,
            council_runtime=self._council_runtime,
        ).execute(session=session, context=context, message=goal)
        output = str(result.events[-1].payload["text"])
        console.print(output)
        return output

    async def _load_or_start_session(
        self,
        *,
        resume: str | None,
        permission_mode: PermissionMode,
        goal: str | None,
    ) -> ChatSession:
        if resume is not None:
            result = await ResumeChatSessionUseCase(
                session_store=self._session_store,
            ).execute(resume)
            return result.session
        result = await StartChatSessionUseCase(session_store=self._session_store).execute(
            goal=goal,
            permission_mode=permission_mode,
            session_id=self._new_session_id(),
        )
        return result.session

    async def _discover_context(self, session: ChatSession) -> tuple[ChatSession, ContextIndex]:
        result = await DiscoverWorkspaceContextUseCase(
            context_discovery=self._context_discovery,
            session_store=self._session_store,
        ).execute(workspace_root=str(self._workspace_root), session=session)
        return result.session or session, result.index

    def _new_session_id(self) -> str:
        return uuid.uuid4().hex[:12]
