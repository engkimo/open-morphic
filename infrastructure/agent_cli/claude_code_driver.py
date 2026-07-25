"""ClaudeCodeDriver — runs tasks via `claude -p` CLI (headless mode)."""

from __future__ import annotations

import json
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
from infrastructure.agent_cli.claude_jsonl import ClaudeJsonlEventDecoder, parse_claude_output


class ClaudeCodeDriver(SubprocessMixin, ResumableStreamingScopedAgentEnginePort):
    """Agent engine backed by Claude Code CLI (headless).

    Executes `claude -p <task> --output-format json` and parses structured output.
    Falls back to raw stdout when JSON parsing fails.
    """

    engine_type: AgentEngineType = AgentEngineType.CLAUDE_CODE

    def __init__(self, enabled: bool = True, cli_path: str = "claude") -> None:
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
                engine=AgentEngineType.CLAUDE_CODE,
                success=False,
                output="",
                error="Claude Code driver is disabled",
            )

        claude_mode = self._permission_mode(permission_mode)
        if claude_mode is None:
            return AgentEngineResult(
                engine=AgentEngineType.CLAUDE_CODE,
                success=False,
                output="",
                error=(
                    "Claude Code headless mode cannot preserve confirm-destructive "
                    "approval prompts"
                ),
            )

        cmd = [
            self._cli_path,
            "-p",
            task,
            "--output-format",
            "stream-json" if event_sink is not None else "json",
            "--max-turns",
            "10",
            "--permission-mode",
            claude_mode,
        ]
        if permission_mode is PermissionMode.DANGER_FULL_ACCESS:
            cmd.append("--dangerously-skip-permissions")
        if resume_session_id:
            cmd.extend(["--resume", resume_session_id])
        if model:
            cmd.extend(["--model", model])

        start = time.monotonic()
        if event_sink is None:
            cli_result = await self._run_cli(
                cmd, timeout=timeout_seconds, cwd=workspace_root
            )
        else:
            decoder = ClaudeJsonlEventDecoder()

            async def publish_line(line: str) -> None:
                for event in decoder.decode(line):
                    await event_sink.publish(event)

            cli_result = await self._run_cli_streaming(
                cmd,
                timeout=timeout_seconds,
                on_stdout_line=publish_line,
                cwd=workspace_root,
            )
        duration = time.monotonic() - start

        if event_sink is not None:
            parsed = parse_claude_output(cli_result.stdout)
            metadata = {
                "events": [event.model_dump(mode="json") for event in parsed.events]
            }
            if parsed.session_id:
                metadata["session_id"] = parsed.session_id
            if parsed.usage:
                metadata["usage"] = parsed.usage
            if parsed.parse_errors:
                metadata["parse_errors"] = parsed.parse_errors
            return AgentEngineResult(
                engine=AgentEngineType.CLAUDE_CODE,
                success=cli_result.returncode == 0 and parsed.error is None,
                output=parsed.output,
                error=parsed.error or (cli_result.stderr if cli_result.returncode else None),
                cost_usd=parsed.cost_usd,
                duration_seconds=duration,
                model_used=parsed.model or model,
                metadata=metadata,
            )

        if cli_result.returncode != 0:
            return AgentEngineResult(
                engine=AgentEngineType.CLAUDE_CODE,
                success=False,
                output=cli_result.stdout,
                error=cli_result.stderr or f"Exit code {cli_result.returncode}",
                duration_seconds=duration,
            )

        # Try JSON parse for structured output
        output_text = cli_result.stdout
        metadata: dict = {}
        model_used: str | None = model
        try:
            data = json.loads(cli_result.stdout)
            output_text = data.get("result", cli_result.stdout)
            if "session_id" in data:
                metadata["session_id"] = data["session_id"]
            if "usage" in data:
                metadata["usage"] = data["usage"]
            if "model" in data:
                model_used = data["model"]
        except (json.JSONDecodeError, TypeError):
            pass  # Use raw stdout

        cost_usd = EngineCostCalculator.calculate(model_used, metadata.get("usage"))

        return AgentEngineResult(
            engine=AgentEngineType.CLAUDE_CODE,
            success=True,
            output=output_text,
            cost_usd=cost_usd,
            duration_seconds=duration,
            model_used=model_used,
            metadata=metadata,
        )

    def _permission_mode(self, permission_mode: PermissionMode) -> str | None:
        if permission_mode is PermissionMode.READ_ONLY:
            return "plan"
        if permission_mode is PermissionMode.WORKSPACE_WRITE:
            return "acceptEdits"
        if permission_mode is PermissionMode.DANGER_FULL_ACCESS:
            return "bypassPermissions"
        return None

    async def is_available(self) -> bool:
        return self._enabled and self._check_cli_exists(self._cli_path)

    def get_capabilities(self) -> AgentEngineCapabilities:
        return AgentEngineCapabilities(
            engine_type=AgentEngineType.CLAUDE_CODE,
            max_context_tokens=200_000,
            supports_sandbox=False,
            supports_parallel=True,
            supports_mcp=True,
            supports_streaming=True,
            cost_per_hour_usd=3.0,
        )
