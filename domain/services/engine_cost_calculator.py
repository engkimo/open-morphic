"""EngineCostCalculator — compute cost from engine usage metadata.

Pure domain service: model name + token counts → cost in USD.
Used by CLI drivers to populate AgentEngineResult.cost_usd from
the ``usage`` dict parsed from JSON output.
"""

from __future__ import annotations

from dataclasses import dataclass

# Pricing per 1 million tokens (input, output).
# Updated 2026-03 — verify periodically against provider pricing pages.
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-6": (15.00, 75.00),
    "claude-haiku-4-5-20251001": (0.25, 1.25),
    # OpenAI
    "o4-mini": (1.10, 4.40),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    # Google
    "gemini/gemini-2.5-pro": (1.25, 10.00),
    "gemini/gemini-2.5-flash": (0.15, 0.60),
    "gemini/gemini-3-pro-preview": (1.25, 10.00),
    "gemini/gemini-3-flash-preview": (0.10, 0.40),
}

# Alias map: normalises common model strings to canonical keys.
_ALIASES: dict[str, str] = {
    "claude-sonnet-4-6": "claude-sonnet-4-6",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
    "haiku": "claude-haiku-4-5-20251001",
    "gpt-4o": "gpt-4o",
    "gpt-4o-mini": "gpt-4o-mini",
    "o4-mini": "o4-mini",
}

# Default medium-tier pricing when model is unknown.
_DEFAULT_PRICING: tuple[float, float] = (3.00, 15.00)


@dataclass(frozen=True)
class UsageCost:
    """Computed cost breakdown."""

    input_tokens: int
    output_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float


class EngineCostCalculator:
    """Stateless calculator — all methods are pure functions."""

    @staticmethod
    def calculate(
        model: str | None,
        usage: dict | None,
    ) -> float:
        """Return cost in USD from a ``usage`` dict.

        *usage* is expected to contain ``prompt_tokens`` and/or
        ``completion_tokens`` (the format used by LiteLLM and most CLIs).

        Returns ``0.0`` when usage data is missing or the model is local.
        """
        if not usage:
            return 0.0

        prompt_tokens = _int_or_zero(usage.get("prompt_tokens") or usage.get("input_tokens"))
        completion_tokens = _int_or_zero(
            usage.get("completion_tokens") or usage.get("output_tokens")
        )

        if prompt_tokens == 0 and completion_tokens == 0:
            return 0.0

        input_price, output_price = _resolve_pricing(model)
        cost = (prompt_tokens / 1_000_000) * input_price + (
            completion_tokens / 1_000_000
        ) * output_price
        return round(cost, 6)

    @staticmethod
    def calculate_detailed(
        model: str | None,
        usage: dict | None,
    ) -> UsageCost:
        """Return a detailed cost breakdown."""
        if not usage:
            return UsageCost(0, 0, 0.0, 0.0, 0.0)

        prompt_tokens = _int_or_zero(usage.get("prompt_tokens") or usage.get("input_tokens"))
        completion_tokens = _int_or_zero(
            usage.get("completion_tokens") or usage.get("output_tokens")
        )

        input_price, output_price = _resolve_pricing(model)
        input_cost = round((prompt_tokens / 1_000_000) * input_price, 6)
        output_cost = round((completion_tokens / 1_000_000) * output_price, 6)
        return UsageCost(
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            total_cost_usd=round(input_cost + output_cost, 6),
        )

    @staticmethod
    def estimate_from_duration(
        cost_per_hour_usd: float,
        duration_seconds: float,
    ) -> float:
        """Fallback: estimate cost from capabilities cost_per_hour * duration."""
        if cost_per_hour_usd <= 0.0 or duration_seconds <= 0.0:
            return 0.0
        return round((cost_per_hour_usd / 3600.0) * duration_seconds, 6)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_pricing(model: str | None) -> tuple[float, float]:
    """Resolve (input_per_M, output_per_M) for *model*."""
    if model is None:
        return _DEFAULT_PRICING

    # Local models are free.
    if model.startswith("ollama/"):
        return (0.0, 0.0)

    # Direct lookup
    if model in _MODEL_PRICING:
        return _MODEL_PRICING[model]

    # Try alias
    canonical = _ALIASES.get(model)
    if canonical and canonical in _MODEL_PRICING:
        return _MODEL_PRICING[canonical]

    # Substring match (e.g. "claude-sonnet-4-6-20260101")
    for key, pricing in _MODEL_PRICING.items():
        if key in model or model in key:
            return pricing

    return _DEFAULT_PRICING


def _int_or_zero(value: object) -> int:
    """Coerce *value* to int, defaulting to 0 on any failure."""
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
