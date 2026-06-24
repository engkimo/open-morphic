"""ExecuteSlashCommandUseCase — handle chat slash commands."""

from __future__ import annotations

from dataclasses import dataclass

from domain.entities.chat_event import ChatEvent, ChatEventType
from domain.entities.chat_session import ChatSession
from domain.entities.workspace_context import ContextIndex
from domain.ports.chat_session_store import ChatSessionStorePort
from domain.ports.engine_registry import EngineRegistryPort


@dataclass(frozen=True)
class ExecuteSlashCommandResult:
    session: ChatSession
    output: str
    events: list[ChatEvent]
    should_exit: bool = False


class ExecuteSlashCommandUseCase:
    def __init__(
        self,
        *,
        session_store: ChatSessionStorePort,
        engine_registry: EngineRegistryPort,
    ) -> None:
        self._session_store = session_store
        self._engine_registry = engine_registry

    async def execute(
        self,
        *,
        session: ChatSession,
        command: str,
        context: ContextIndex | None = None,
    ) -> ExecuteSlashCommandResult:
        command_name = command.strip().split(maxsplit=1)[0]
        if not command_name.startswith("/"):
            raise ValueError("slash command must start with '/'")

        current, command_event = session.record_event(
            ChatEventType.SLASH_COMMAND,
            {"command": command},
        )
        output, should_exit = await self._render_command(
            command_name,
            current,
            context,
        )
        events = [command_event]

        if should_exit:
            current, ended_event = current.record_event(
                ChatEventType.SESSION_ENDED,
                {"reason": "user_quit"},
            )
            current = current.close()
            events.append(ended_event)
        else:
            current, assistant_event = current.record_event(
                ChatEventType.ASSISTANT_MESSAGE,
                {"text": output, "source": command_name},
            )
            events.append(assistant_event)

        for event in events:
            await self._session_store.append_event(event)

        return ExecuteSlashCommandResult(
            session=current,
            output=output,
            events=events,
            should_exit=should_exit,
        )

    async def _render_command(
        self,
        command_name: str,
        session: ChatSession,
        context: ContextIndex | None,
    ) -> tuple[str, bool]:
        if command_name == "/help":
            return (
                "/help /status /context /engines /diff /quit",
                False,
            )
        if command_name == "/status":
            return (
                f"session={session.id} status={session.status.value} "
                f"mode={session.permission_mode.value} next={session.next_sequence}",
                False,
            )
        if command_name == "/context":
            source_count = 0 if context is None else len(context.sources)
            return (f"context_sources={source_count}", False)
        if command_name == "/engines":
            engines = await self._engine_registry.list_engines()
            return (
                "\n".join(
                    f"{engine.id}: {engine.display_name} available={engine.available}"
                    for engine in engines
                ),
                False,
            )
        if command_name == "/diff":
            return ("no proposed diff", False)
        if command_name == "/quit":
            return ("session ended", True)
        return (f"unknown command: {command_name}", False)
