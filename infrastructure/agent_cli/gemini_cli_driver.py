"""GeminiCLIDriver — runs tasks via `gemini` CLI."""

from __future__ import annotations

import json
import os
import time

from domain.ports.agent_engine import (
    AgentEngineCapabilities,
    AgentEnginePort,
    AgentEngineResult,
)
from domain.services.engine_cost_calculator import EngineCostCalculator
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.agent_cli._subprocess_base import SubprocessMixin


class GeminiCLIDriver(SubprocessMixin, AgentEnginePort):
    """Agent engine backed by Gemini CLI.

    Executes `gemini -p <task> --output-format json` for 2M token context tasks.
    """

    engine_type: AgentEngineType = AgentEngineType.GEMINI_CLI

    def __init__(
        self,
        enabled: bool = True,
        cli_path: str = "gemini",
        api_key: str | None = None,
    ) -> None:
        self._enabled = enabled
        self._cli_path = cli_path
        self._api_key = api_key

    def _resolve_api_key(self) -> str | None:
        """Return the API key from constructor arg or environment variables."""
        return (
            self._api_key
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_GEMINI_API_KEY")
        )

    def _build_env(self) -> dict[str, str] | None:
        """Build subprocess environment with GEMINI_API_KEY injected."""
        key = self._resolve_api_key()
        if not key:
            return None
        env = os.environ.copy()
        env["GEMINI_API_KEY"] = key
        return env

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
            # Strip LiteLLM provider prefix (e.g. "gemini/gemini-3-pro-preview"
            # → "gemini-3-pro-preview"). The CLI expects bare model names.
            cli_model = model.split("/", 1)[-1] if "/" in model else model
            cmd.extend(["-m", cli_model])

        start = time.monotonic()
        cli_result = await self._run_cli(cmd, timeout=timeout_seconds, env=self._build_env())
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
            # Gemini CLI uses "response" key; fall back to "result" for compat
            output_text = data.get("response") or data.get("result") or cli_result.stdout
            if "model" in data:
                model_used = data["model"]
            # Extract model name and usage from stats.models when present
            stats_models = (data.get("stats") or {}).get("models") or {}
            if stats_models:
                metadata["models"] = stats_models
                # Aggregate token usage across all models used in the session
                total_input = 0
                total_output = 0
                primary_model: str | None = None
                for mname, mstats in stats_models.items():
                    tokens = mstats.get("tokens") or {}
                    total_input += tokens.get("input", 0)
                    total_output += tokens.get("candidates", 0)
                    # Pick the "main" role model or the first one as primary
                    roles = mstats.get("roles") or {}
                    if "main" in roles and primary_model is None:
                        primary_model = mname
                if primary_model and model_used is None:
                    model_used = primary_model
                if total_input or total_output:
                    metadata["usage"] = {
                        "input_tokens": total_input,
                        "output_tokens": total_output,
                    }
            if "usage" in data:
                metadata["usage"] = data["usage"]
        except (json.JSONDecodeError, TypeError):
            pass

        cost_usd = EngineCostCalculator.calculate(model_used, metadata.get("usage"))

        return AgentEngineResult(
            engine=AgentEngineType.GEMINI_CLI,
            success=True,
            output=output_text,
            cost_usd=cost_usd,
            duration_seconds=duration,
            model_used=model_used,
            metadata=metadata,
        )

    async def is_available(self) -> bool:
        return (
            self._enabled
            and self._check_cli_exists(self._cli_path)
            and self._resolve_api_key() is not None
        )

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
