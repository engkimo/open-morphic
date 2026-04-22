"""ClaudeCodeDriver — runs tasks via `claude -p` CLI (headless mode)."""

from __future__ import annotations

import json
import time

from domain.ports.agent_engine import (
    AgentEngineCapabilities,
    AgentEnginePort,
    AgentEngineResult,
)
from domain.services.engine_cost_calculator import EngineCostCalculator
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.agent_cli._subprocess_base import SubprocessMixin


class ClaudeCodeDriver(SubprocessMixin, AgentEnginePort):
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
        if not self._enabled:
            return AgentEngineResult(
                engine=AgentEngineType.CLAUDE_CODE,
                success=False,
                output="",
                error="Claude Code driver is disabled",
            )

        cmd = [
            self._cli_path,
            "-p",
            task,
            "--output-format",
            "json",
            "--max-turns",
            "10",
            "--setting-sources",
            "user",
            "--allowedTools",
            "Bash,Read,Write,Edit,WebFetch,WebSearch",
        ]
        if model:
            cmd.extend(["--model", model])

        start = time.monotonic()
        cli_result = await self._run_cli(cmd, timeout=timeout_seconds)
        duration = time.monotonic() - start

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
