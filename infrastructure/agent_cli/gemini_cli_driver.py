"""GeminiCLIDriver — runs tasks via `gemini` CLI."""

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


class GeminiCLIDriver(SubprocessMixin, AgentEnginePort):
    """Agent engine backed by Gemini CLI.

    Executes `gemini -p <task> --output-format json` for 2M token context tasks.
    """

    engine_type: AgentEngineType = AgentEngineType.GEMINI_CLI

    def __init__(self, enabled: bool = True, cli_path: str = "gemini") -> None:
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
                engine=AgentEngineType.GEMINI_CLI,
                success=False,
                output="",
                error="Gemini CLI driver is disabled",
            )

        cmd = [self._cli_path, "-p", task, "--output-format", "json"]
        if model:
            cmd.extend(["-m", model])

        start = time.monotonic()
        cli_result = await self._run_cli(cmd, timeout=timeout_seconds)
        duration = time.monotonic() - start

        if cli_result.returncode != 0:
            return AgentEngineResult(
                engine=AgentEngineType.GEMINI_CLI,
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
            engine=AgentEngineType.GEMINI_CLI,
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
            engine_type=AgentEngineType.GEMINI_CLI,
            max_context_tokens=2_000_000,
            supports_sandbox=False,
            supports_parallel=False,
            supports_mcp=True,
            supports_streaming=True,
            cost_per_hour_usd=0.0,
        )
