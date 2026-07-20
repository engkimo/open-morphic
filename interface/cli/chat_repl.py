"""Line-oriented REPL for Morphic Chat CLI."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from application.use_cases.discover_workspace_context import DiscoverWorkspaceContextUseCase
from application.use_cases.execute_chat_hook import ExecuteChatHookUseCase
from application.use_cases.execute_chat_tool import ExecuteChatToolUseCase
from application.use_cases.execute_slash_command import ExecuteSlashCommandUseCase
from application.use_cases.resume_chat_session import ResumeChatSessionUseCase
from application.use_cases.send_chat_message import SendChatMessageUseCase
from application.use_cases.start_chat_session import StartChatSessionUseCase
from domain.entities.chat_event import ChatEventType
from domain.entities.chat_session import ChatSession, PermissionMode
from domain.entities.council_runtime import CouncilTurn
from domain.entities.execution import Action
from domain.entities.hook import HookType
from domain.entities.workspace_context import ContextIndex
from domain.ports.agent_engine import AgentEngineEventSinkPort
from domain.ports.council_runtime import CouncilRuntimePort
from domain.ports.engine_registry import EngineRegistryPort
from domain.ports.hook_executor import HookExecutorPort
from domain.ports.tool_executor import ToolExecutorPort
from domain.services.risk_assessor import RiskAssessor
from infrastructure.chat.jsonl_session_store import JsonlChatSessionStore
from infrastructure.context.workspace_context_discovery import WorkspaceContextDiscovery
from infrastructure.council.local_chat_council_runtime import LocalChatCouncilRuntime
from infrastructure.engines.static_engine_registry import StaticEngineRegistry
from infrastructure.hooks.noop_hook_executor import NoopHookExecutor
from infrastructure.hooks.workspace_hook_registry import WorkspaceHookRegistry
from infrastructure.tools.noop_tool_executor import NoopToolExecutor
from interface.cli.chat_control_transport import ChatControlServer
from interface.cli.formatters import console
from interface.cli.native_event_progress import NativeEventProgressRenderer
from interface.cli.slash_commands import parse_slash_command
from interface.cli.turn_control import ActiveTurnController, TurnCancelledError


@dataclass(frozen=True)
class GoalRunResult:
    output: str
    turns: tuple[CouncilTurn, ...]


class ChatRepl:
    """Portable line-oriented chat loop."""

    def __init__(
        self,
        *,
        workspace_root: Path,
        council_runtime: CouncilRuntimePort | None = None,
        engine_registry: EngineRegistryPort | None = None,
        hook_executor_factory: Callable[[Path], HookExecutorPort] | None = None,
        tool_executor_factory: Callable[[Path], ToolExecutorPort] | None = None,
        engine_event_observer: AgentEngineEventSinkPort | None = None,
        turn_controller: ActiveTurnController | None = None,
        control_enabled: bool = False,
    ) -> None:
        self._workspace_root = workspace_root
        self._session_store = JsonlChatSessionStore(workspace_root=workspace_root)
        self._context_discovery = WorkspaceContextDiscovery()
        self._council_runtime = council_runtime or LocalChatCouncilRuntime()
        self._engine_registry = engine_registry or StaticEngineRegistry()
        self._hook_executor_factory = hook_executor_factory or (lambda _root: NoopHookExecutor())
        self._tool_executor_factory = tool_executor_factory or (lambda _root: NoopToolExecutor())
        self._risk_assessor = RiskAssessor()
        self._engine_event_observer = (
            engine_event_observer or NativeEventProgressRenderer()
        )
        self._turn_controller = turn_controller or ActiveTurnController()
        self._control_enabled = control_enabled

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
        queued_line: str | None = None

        while True:
            is_steered = queued_line is not None
            if is_steered:
                line = queued_line
                queued_line = None
            else:
                try:
                    line = input("> ")
                except EOFError:
                    break
            if not line.strip():
                continue
            if not is_steered and line.strip().startswith("/"):
                if line.strip().startswith("/hooks "):
                    session, output = await self._execute_hooks_command(session, line)
                    console.print(output)
                    continue
                if line.strip().startswith("/tools "):
                    session, output = await self._execute_tools_command(session, line)
                    console.print(output)
                    continue
                result = await ExecuteSlashCommandUseCase(
                    session_store=self._session_store,
                    engine_registry=self._engine_registry,
                ).execute(session=session, command=line, context=context)
                session = result.session
                console.print(result.output)
                if result.should_exit:
                    break
                continue

            try:
                send_message = SendChatMessageUseCase(
                    session_store=self._session_store,
                    council_runtime=self._council_runtime,
                    engine_event_observer=self._engine_event_observer,
                ).execute
                operation = partial(
                    send_message,
                    session=session,
                    context=context,
                    message=line,
                )
                if self._control_enabled:
                    async with ChatControlServer(
                        workspace_root=self._workspace_root,
                        session_id=session.id,
                        turn_controller=self._turn_controller,
                    ):
                        result = await self._turn_controller.run(operation)
                else:
                    result = await self._turn_controller.run(operation)
            except TurnCancelledError:
                resumed = await ResumeChatSessionUseCase(
                    session_store=self._session_store,
                ).execute(session.id)
                session = resumed.session
                queued_line = self._turn_controller.take_steer_prompt()
                if queued_line is None:
                    console.print("Turn cancelled.")
                else:
                    session, steered_event = session.record_event(
                        ChatEventType.TURN_STEERED,
                        {
                            "replacement_prompt_bytes": len(
                                queued_line.encode("utf-8")
                            ),
                            "source": "turn_controller",
                        },
                    )
                    await self._session_store.append_event(steered_event)
                    console.print("Turn steered.")
                continue
            session = result.session
            console.print(result.events[-1].payload["text"])

        return session

    async def run_goal(
        self,
        *,
        goal: str,
        permission_mode: PermissionMode = PermissionMode.CONFIRM_DESTRUCTIVE,
    ) -> str:
        return (
            await self.run_goal_with_result(
                goal=goal,
                permission_mode=permission_mode,
            )
        ).output

    async def run_goal_with_result(
        self,
        *,
        goal: str,
        permission_mode: PermissionMode = PermissionMode.CONFIRM_DESTRUCTIVE,
    ) -> GoalRunResult:
        session = await self._load_or_start_session(
            resume=None,
            permission_mode=permission_mode,
            goal=goal,
        )
        session, context = await self._discover_context(session)
        result = await SendChatMessageUseCase(
            session_store=self._session_store,
            council_runtime=self._council_runtime,
            engine_event_observer=self._engine_event_observer,
        ).execute(session=session, context=context, message=goal)
        output = str(result.events[-1].payload["text"])
        console.print(output)
        return GoalRunResult(output=output, turns=result.turns)

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

    async def _execute_hooks_command(
        self,
        session: ChatSession,
        line: str,
    ) -> tuple[ChatSession, str]:
        command = parse_slash_command(line)
        verb, _, raw_hook_type = command.args.partition(" ")
        if verb != "run" or not raw_hook_type:
            return session, "usage: /hooks run <hook_type>"

        try:
            hook_type = HookType(raw_hook_type)
        except ValueError:
            valid = ", ".join(item.value for item in HookType)
            return session, f"invalid hook type: {raw_hook_type} expected one of: {valid}"

        current, command_event = session.record_event(
            ChatEventType.SLASH_COMMAND,
            {"command": line},
        )
        await self._session_store.append_event(command_event)

        hook_executor = self._hook_executor_factory(self._workspace_root)
        hook_result = await ExecuteChatHookUseCase(
            session_store=self._session_store,
            hook_registry=WorkspaceHookRegistry(self._workspace_root),
            hook_executor=hook_executor,
        ).execute(session=current, hook_type=hook_type)
        current = hook_result.session

        skipped = sum(
            1 for event in hook_result.events if event.type is ChatEventType.HOOK_EXECUTION_SKIPPED
        )
        failed = sum(1 for result in hook_result.hook_results if not result.success)
        succeeded = sum(1 for result in hook_result.hook_results if result.success)
        mode = "shell" if hook_executor.__class__.__name__ == "ShellHookExecutor" else "noop"
        output = (
            f"hooks type={hook_type.value} mode={mode} "
            f"succeeded={succeeded} failed={failed} skipped={skipped}"
        )
        current, assistant_event = current.record_event(
            ChatEventType.ASSISTANT_MESSAGE,
            {"text": output, "source": "/hooks"},
        )
        await self._session_store.append_event(assistant_event)
        return current, output

    async def _execute_tools_command(
        self,
        session: ChatSession,
        line: str,
    ) -> tuple[ChatSession, str]:
        command = parse_slash_command(line)
        verb, _, rest = command.args.partition(" ")
        tool_name, _, raw_arguments = rest.partition(" ")
        if verb != "run" or not tool_name:
            return session, "usage: /tools run <tool_name> [json_arguments]"

        try:
            arguments = self._parse_tool_arguments(raw_arguments)
        except ValueError as exc:
            return session, str(exc)

        current, command_event = session.record_event(
            ChatEventType.SLASH_COMMAND,
            {"command": line},
        )
        await self._session_store.append_event(command_event)

        hook_executor = self._hook_executor_factory(self._workspace_root)
        hook_runner = ExecuteChatHookUseCase(
            session_store=self._session_store,
            hook_registry=WorkspaceHookRegistry(self._workspace_root),
            hook_executor=hook_executor,
        )
        tool_executor = self._tool_executor_factory(self._workspace_root)
        try:
            result = await ExecuteChatToolUseCase(
                session_store=self._session_store,
                tool_executor=tool_executor,
                hook_runner=hook_runner,
            ).execute(
                session=current,
                tool_name=tool_name,
                arguments=arguments,
                risk_level=self._risk_assessor.assess(
                    Action(tool=tool_name, args=arguments)
                ),
            )
        except PermissionError as exc:
            output = f"permission denied: {exc}"
            current, assistant_event = current.record_event(
                ChatEventType.ASSISTANT_MESSAGE,
                {"text": output, "source": "/tools"},
            )
            await self._session_store.append_event(assistant_event)
            return current, output
        current = result.session

        mode = "laee" if tool_executor.__class__.__name__ == "LaeeToolExecutor" else "noop"
        output = self._format_tool_output(
            tool_name=tool_name,
            mode=mode,
            success=result.tool_result.success,
            exit_code=result.tool_result.exit_code,
            stderr_summary=result.tool_result.stderr_summary,
        )
        current, assistant_event = current.record_event(
            ChatEventType.ASSISTANT_MESSAGE,
            {"text": output, "source": "/tools"},
        )
        await self._session_store.append_event(assistant_event)
        return current, output

    def _format_tool_output(
        self,
        *,
        tool_name: str,
        mode: str,
        success: bool,
        exit_code: int | None,
        stderr_summary: str,
    ) -> str:
        output = f"tools tool={tool_name} mode={mode} success={success}"
        if exit_code is not None:
            output = f"{output} exit_code={exit_code}"
        if not success and stderr_summary:
            output = f"{output} error={stderr_summary}"
        return output

    def _parse_tool_arguments(self, raw_arguments: str) -> dict[str, Any]:
        if not raw_arguments:
            return {}
        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON arguments: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("invalid JSON arguments: expected object")
        return parsed
