"""CodexCLIDriver — runs tasks via `codex exec` CLI."""

from __future__ import annotations

import time

from domain.entities.chat_session import PermissionMode
from domain.ports.agent_engine import (
    AgentEngineCapabilities,
    AgentEngineEventSinkPort,
    AgentEngineResult,
    ResumableStreamingScopedAgentEnginePort,
)
from domain.services.engine_cost_calculator import EngineCostCalculator
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.agent_cli._subprocess_base import SubprocessMixin
from infrastructure.agent_cli.codex_jsonl import CodexJsonlEventDecoder, parse_codex_output


class CodexCLIDriver(SubprocessMixin, ResumableStreamingScopedAgentEnginePort):
    """Agent engine backed by OpenAI Codex CLI.

    Executes `codex exec --json` with an explicit sandbox and parses JSONL output.
    """

    engine_type: AgentEngineType = AgentEngineType.CODEX_CLI

    def __init__(self, enabled: bool = True, cli_path: str = "codex") -> None:
        self._enabled = enabled
        self._cli_path = cli_path

    async def run_task(
        self,
        task: str,
        model: str | None = None,
        timeout_seconds: float = 300.0,
    ) -> AgentEngineResult:
        return await self._run_task(
            task=task,
            model=model,
            timeout_seconds=timeout_seconds,
            workspace_root=None,
            permission_mode=PermissionMode.READ_ONLY,
        )

    async def run_task_scoped(
        self,
        task: str,
        *,
        workspace_root: str,
        permission_mode: PermissionMode,
        model: str | None = None,
        timeout_seconds: float = 300.0,
    ) -> AgentEngineResult:
        return await self._run_task(
            task=task,
            model=model,
            timeout_seconds=timeout_seconds,
            workspace_root=workspace_root,
            permission_mode=permission_mode,
            event_sink=None,
        )

    async def run_task_scoped_stream(
        self,
        task: str,
        *,
        workspace_root: str,
        permission_mode: PermissionMode,
        event_sink: AgentEngineEventSinkPort,
        model: str | None = None,
        timeout_seconds: float = 300.0,
    ) -> AgentEngineResult:
        return await self._run_task(
            task=task,
            model=model,
            timeout_seconds=timeout_seconds,
            workspace_root=workspace_root,
            permission_mode=permission_mode,
            event_sink=event_sink,
        )

    async def resume_task_scoped_stream(
        self,
        task: str,
        *,
        resume_session_id: str,
        workspace_root: str,
        permission_mode: PermissionMode,
        event_sink: AgentEngineEventSinkPort,
        model: str | None = None,
        timeout_seconds: float = 300.0,
    ) -> AgentEngineResult:
        return await self._run_task(
            task=task,
            model=model,
            timeout_seconds=timeout_seconds,
            workspace_root=workspace_root,
            permission_mode=permission_mode,
            event_sink=event_sink,
            resume_session_id=resume_session_id,
        )

    async def _run_task(
        self,
        *,
        task: str,
        model: str | None,
        timeout_seconds: float,
        workspace_root: str | None,
        permission_mode: PermissionMode,
        event_sink: AgentEngineEventSinkPort | None = None,
        resume_session_id: str | None = None,
    ) -> AgentEngineResult:
        if not self._enabled:
            return AgentEngineResult(
                engine=AgentEngineType.CODEX_CLI,
                success=False,
                output="",
                error="Codex CLI driver is disabled",
            )

        sandbox = self._sandbox_for(permission_mode)
        if sandbox is None:
            return AgentEngineResult(
                engine=AgentEngineType.CODEX_CLI,
                success=False,
                output="",
                error=(
                    "Codex non-interactive mode cannot preserve "
                    "confirm-destructive approvals; use read-only, workspace-write, "
                    "or danger-full-access"
                ),
            )

        cmd = [self._cli_path, "exec", "--json", "--sandbox", sandbox]
        if workspace_root:
            cmd.extend(["--cd", workspace_root])
        if model:
            cmd.extend(["--model", model])
        if resume_session_id:
            cmd.extend(["resume", resume_session_id])
        cmd.append(task)

        start = time.monotonic()
        if event_sink is None:
            cli_result = await self._run_cli(cmd, timeout=timeout_seconds)
        else:
            decoder = CodexJsonlEventDecoder()

            async def publish_line(line: str) -> None:
                event = decoder.decode(line)
                if event is not None:
                    await event_sink.publish(event)

            cli_result = await self._run_cli_streaming(
                cmd,
                timeout=timeout_seconds,
                on_stdout_line=publish_line,
            )
        duration = time.monotonic() - start

        parsed = parse_codex_output(cli_result.stdout)
        metadata: dict = {
            "events": [event.model_dump(mode="json") for event in parsed.events],
        }
        if parsed.session_id:
            metadata["session_id"] = parsed.session_id
        if parsed.usage:
            metadata["usage"] = parsed.usage
        if parsed.parse_errors:
            metadata["parse_errors"] = parsed.parse_errors

        if cli_result.returncode != 0 or parsed.error:
            return AgentEngineResult(
                engine=AgentEngineType.CODEX_CLI,
                success=False,
                output=parsed.output,
                error=(
                    parsed.error
                    or cli_result.stderr
                    or f"Exit code {cli_result.returncode}"
                ),
                duration_seconds=duration,
                model_used=parsed.model or model,
                metadata=metadata,
            )

        model_used = parsed.model or model

        cost_usd = EngineCostCalculator.calculate(model_used, metadata.get("usage"))

        return AgentEngineResult(
            engine=AgentEngineType.CODEX_CLI,
            success=True,
            output=parsed.output,
            cost_usd=cost_usd,
            duration_seconds=duration,
            model_used=model_used,
            metadata=metadata,
        )

    async def is_available(self) -> bool:
        return self._enabled and self._check_cli_exists(self._cli_path)

    def get_capabilities(self) -> AgentEngineCapabilities:
        return AgentEngineCapabilities(
            engine_type=AgentEngineType.CODEX_CLI,
            max_context_tokens=128_000,
            supports_sandbox=True,
            supports_parallel=True,
            supports_mcp=True,
            supports_streaming=True,
            cost_per_hour_usd=2.0,
        )

    def _sandbox_for(self, permission_mode: PermissionMode | None) -> str | None:
        if permission_mode is None or permission_mode is PermissionMode.READ_ONLY:
            return "read-only"
        if permission_mode is PermissionMode.WORKSPACE_WRITE:
            return "workspace-write"
        if permission_mode is PermissionMode.DANGER_FULL_ACCESS:
            return "danger-full-access"
        return None
