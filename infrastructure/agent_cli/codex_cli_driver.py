"""CodexCLIDriver — runs tasks via `codex exec` CLI."""

from __future__ import annotations

import json
import time

from domain.ports.agent_engine import (
    AgentEngineCapabilities,
    AgentEnginePort,
    AgentEngineResult,
)
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.agent_cli._subprocess_base import SubprocessMixin


class CodexCLIDriver(SubprocessMixin, AgentEnginePort):
    """Agent engine backed by OpenAI Codex CLI.

    Executes `codex exec --json --full-auto <task>` and parses structured output.
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
        if not self._enabled:
            return AgentEngineResult(
                engine=AgentEngineType.CODEX_CLI,
                success=False,
                output="",
                error="Codex CLI driver is disabled",
            )

        cmd = [self._cli_path, "exec", "--json", "--full-auto", task]
        if model:
            cmd.extend(["--model", model])

        start = time.monotonic()
        cli_result = await self._run_cli(cmd, timeout=timeout_seconds)
        duration = time.monotonic() - start

        if cli_result.returncode != 0:
            return AgentEngineResult(
                engine=AgentEngineType.CODEX_CLI,
                success=False,
                output=cli_result.stdout,
                error=cli_result.stderr or f"Exit code {cli_result.returncode}",
                duration_seconds=duration,
            )

        output_text = cli_result.stdout
        metadata: dict = {}
        model_used: str | None = model
        try:
            data = json.loads(cli_result.stdout)
            output_text = data.get("result", cli_result.stdout)
            if "model" in data:
                model_used = data["model"]
            if "usage" in data:
                metadata["usage"] = data["usage"]
        except (json.JSONDecodeError, TypeError):
            pass

        return AgentEngineResult(
            engine=AgentEngineType.CODEX_CLI,
            success=True,
            output=output_text,
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
            supports_streaming=False,
            cost_per_hour_usd=2.0,
        )
