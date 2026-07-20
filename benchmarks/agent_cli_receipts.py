"""Normalize provider output into privacy-preserving benchmark receipts."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from benchmarks.agent_cli_comparison import AgentCliArm
from domain.services.engine_cost_calculator import EngineCostCalculator
from infrastructure.agent_cli.claude_jsonl import parse_claude_output
from infrastructure.agent_cli.codex_jsonl import parse_codex_output


class _FrozenModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid", frozen=True)


class ProviderReceipt(_FrozenModel):
    """Normalized cost/success evidence with provider output removed."""

    provider: AgentCliArm
    success: bool
    model: str = Field(min_length=1)
    usage: dict[str, int]
    cost_usd: float = Field(ge=0.0)
    cost_source: Literal[
        "provider_reported",
        "calculated_from_usage",
        "morphic_reported",
    ]
    parse_errors: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_receipt(self) -> ProviderReceipt:
        if any(tokens < 0 for tokens in self.usage.values()):
            raise ValueError("usage token counts must be non-negative")
        expected_sources = {
            AgentCliArm.CODEX_CLI: "calculated_from_usage",
            AgentCliArm.CLAUDE_CODE: "provider_reported",
            AgentCliArm.MORPHIC_CONTROL: "morphic_reported",
        }
        if self.cost_source != expected_sources[self.provider]:
            raise ValueError("cost_source does not match provider")
        if self.provider is AgentCliArm.CODEX_CLI:
            if not self.usage:
                raise ValueError("Codex calculated receipt requires usage")
            calculated = EngineCostCalculator.calculate(self.model, self.usage)
            if abs(self.cost_usd - calculated) > 0.000001:
                raise ValueError("Codex receipt cost does not match usage")
        return self

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


class _MorphicReceiptEnvelope(_FrozenModel):
    type: Literal["morphic_benchmark_receipt"]
    success: bool
    model: str = Field(min_length=1)
    usage: dict[str, int]
    cost_usd: float = Field(ge=0.0)


class ProviderReceiptParser:
    """Parse supported provider outputs without retaining their raw content."""

    def parse(
        self,
        *,
        arm: AgentCliArm | str,
        stdout: str,
        model_hint: str | None = None,
    ) -> ProviderReceipt | None:
        parsed_arm = AgentCliArm(arm)
        if parsed_arm is AgentCliArm.CODEX_CLI:
            return self._parse_codex(stdout, model_hint=model_hint)
        if parsed_arm is AgentCliArm.CLAUDE_CODE:
            return self._parse_claude(stdout, model_hint=model_hint)
        return self._parse_morphic(stdout)

    def _parse_codex(self, stdout: str, *, model_hint: str | None) -> ProviderReceipt | None:
        parsed = parse_codex_output(stdout)
        model = parsed.model or model_hint
        if not parsed.usage or not model:
            return None
        return ProviderReceipt(
            provider=AgentCliArm.CODEX_CLI,
            success=parsed.error is None,
            model=model,
            usage=parsed.usage,
            cost_usd=EngineCostCalculator.calculate(model, parsed.usage),
            cost_source="calculated_from_usage",
            parse_errors=parsed.parse_errors,
        )

    def _parse_claude(self, stdout: str, *, model_hint: str | None) -> ProviderReceipt | None:
        parsed = parse_claude_output(stdout)
        model = parsed.model or model_hint
        if not model or (not parsed.usage and parsed.cost_usd == 0.0):
            return None
        return ProviderReceipt(
            provider=AgentCliArm.CLAUDE_CODE,
            success=parsed.error is None,
            model=model,
            usage=parsed.usage or {},
            cost_usd=parsed.cost_usd,
            cost_source="provider_reported",
            parse_errors=parsed.parse_errors,
        )

    def _parse_morphic(self, stdout: str) -> ProviderReceipt | None:
        for line in reversed(stdout.splitlines()):
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict) or raw.get("type") != "morphic_benchmark_receipt":
                continue
            try:
                envelope = _MorphicReceiptEnvelope.model_validate(raw)
            except ValueError:
                return None
            return ProviderReceipt(
                provider=AgentCliArm.MORPHIC_CONTROL,
                success=envelope.success,
                model=envelope.model,
                usage=envelope.usage,
                cost_usd=envelope.cost_usd,
                cost_source="morphic_reported",
            )
        return None
