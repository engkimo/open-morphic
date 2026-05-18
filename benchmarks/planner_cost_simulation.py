"""LLMPlanner cost projection: Sonnet 4.6 vs Haiku 4.5, padded vs unpadded.

Pure-math simulation — no live API calls, runs in <1s. Used to evaluate
whether downgrading the planner default model from Sonnet 4.6 to Haiku 4.5
is cost-positive, and whether padding the system prefix to clear the
empirical cache thresholds is worth the extra input tokens.

Inputs measured from current code:
- ``_SYSTEM_PROMPT`` token count (tiktoken cl100k as a stand-in for
  Anthropic's tokenizer — close enough for relative comparisons).

Inputs assumed (override via CLI flags):
- per-call user-message tokens
- per-call output tokens
- steady-state cache hit rate
- monthly call volume

Empirical cache thresholds (haiku_cache_followup_2026_05_15.md):
  Sonnet 4.6: ~2048 tokens
  Haiku 4.5:  ~4096 tokens
  Per-hit savings: ~76% on the cached prefix.

Usage:
    uv run --extra dev python -m benchmarks.planner_cost_simulation
    uv run --extra dev python -m benchmarks.planner_cost_simulation \
        --user-tok 300 --output-tok 800 --hit-rate 0.6
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import tiktoken

from infrastructure.fractal.llm_planner import _SYSTEM_PROMPT


@dataclass(frozen=True)
class ModelPricing:
    """Anthropic public pricing in USD per 1M tokens."""

    name: str
    input_per_m: float
    output_per_m: float
    cache_threshold_tok: int


# Anthropic public pricing (2026-05). Cache write = 1.25x input, read = 0.10x.
SONNET_4_6 = ModelPricing("sonnet_4_6", 3.00, 15.00, 2048)
HAIKU_4_5 = ModelPricing("haiku_4_5", 1.00, 5.00, 4096)
CACHE_WRITE_MUL = 1.25
CACHE_READ_MUL = 0.10


def per_call_cost(
    pricing: ModelPricing,
    *,
    system_tok: int,
    user_tok: int,
    output_tok: int,
    padded: bool,
    hit_rate: float,
) -> tuple[float, float]:
    """Return (first_call_cost, steady_state_call_cost) in USD."""
    sys_billed = max(system_tok, pricing.cache_threshold_tok) if padded else system_tok
    out_cost = output_tok / 1e6 * pricing.output_per_m

    if not padded:
        # Below cache threshold → full input price every call.
        cost = (sys_billed + user_tok) / 1e6 * pricing.input_per_m + out_cost
        return cost, cost

    first = (
        sys_billed / 1e6 * pricing.input_per_m * CACHE_WRITE_MUL
        + user_tok / 1e6 * pricing.input_per_m
        + out_cost
    )
    hit = (
        sys_billed / 1e6 * pricing.input_per_m * CACHE_READ_MUL
        + user_tok / 1e6 * pricing.input_per_m
        + out_cost
    )
    miss = (sys_billed + user_tok) / 1e6 * pricing.input_per_m + out_cost
    steady = hit_rate * hit + (1 - hit_rate) * miss
    return first, steady


def _measure_system_tok() -> int:
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(_SYSTEM_PROMPT))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--user-tok", type=int, default=200,
                   help="Per-call user-message tokens (direction/level/context/goal).")
    p.add_argument("--output-tok", type=int, default=600,
                   help="Per-call output tokens (typical 3 candidates × ~200 tok).")
    p.add_argument("--hit-rate", type=float, default=0.80,
                   help="Steady-state cache hit rate (empirical 0.795 padded).")
    p.add_argument("--volumes", type=int, nargs="+", default=[10, 100, 1000],
                   help="Daily call volumes to project monthly cost for.")
    args = p.parse_args()

    sys_tok = _measure_system_tok()
    print("=== LLMPlanner Cost Simulation ===")
    print(
        f"_SYSTEM_PROMPT: {sys_tok} tok | "
        f"user avg: {args.user_tok} tok | "
        f"output avg: {args.output_tok} tok"
    )
    print(f"Steady-state cache hit rate (padded only): {args.hit_rate:.0%}")
    print()
    print(f"{'Scenario':<35}  {'1st call':>10}  {'steady':>10}  {'Δ vs Sonnet':>14}")
    print("-" * 75)

    baseline_steady: float | None = None
    rows: list[tuple[str, float, float]] = []
    for pricing in (SONNET_4_6, HAIKU_4_5):
        for padded in (False, True):
            first, steady = per_call_cost(
                pricing,
                system_tok=sys_tok,
                user_tok=args.user_tok,
                output_tok=args.output_tok,
                padded=padded,
                hit_rate=args.hit_rate,
            )
            label = f"{pricing.name} ({'padded' if padded else 'unpadded'})"
            rows.append((label, first, steady))
            if baseline_steady is None:
                baseline_steady = steady
            delta = (steady - baseline_steady) / baseline_steady * 100
            print(f"{label:<35}  ${first:>9.6f}  ${steady:>9.6f}  {delta:+13.1f}%")

    sonnet_unpadded = rows[0][2]
    haiku_unpadded = rows[2][2]
    haiku_padded = rows[3][2]

    print()
    print("=== Monthly Volume Projection (steady state) ===")
    for daily in args.volumes:
        monthly = daily * 30
        print(f"  {daily:>5}/day = {monthly:>6}/month:")
        print(f"    Sonnet unpadded: ${monthly * sonnet_unpadded:>8.2f}")
        print(
            f"    Haiku unpadded:  ${monthly * haiku_unpadded:>8.2f}  "
            f"(save ${monthly * (sonnet_unpadded - haiku_unpadded):.2f})"
        )
        print(
            f"    Haiku padded:    ${monthly * haiku_padded:>8.2f}  "
            f"(Δ vs unpadded ${monthly * (haiku_padded - haiku_unpadded):+.2f})"
        )


if __name__ == "__main__":
    main()
