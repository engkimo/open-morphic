"""Live cache_hit_rate baseline (TD-193).

Calls a stable LLMPlanner prompt N times against a real provider that
supports prompt caching, then reads the resulting CostRecord stream from
an in-memory CostRepository to compute the cache_hit_rate.

Pre-conditions:
- TD-188: cached_tokens flow LLM response → CostRecord
- TD-190: LLMPlanner system prompt is byte-stable across calls
- TD-193: LiteLLMGateway injects cache_control on the system message for Claude

Usage:
    uv run --extra dev python -m benchmarks.cache_hit_rate \
        --model claude-haiku-4-5-20251001 --calls 5

Output: human-readable per-call table + summary {cache_hit_rate, total_cost}.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from infrastructure.fractal.llm_planner import LLMPlanner
from infrastructure.llm.cost_tracker import CostTracker
from infrastructure.llm.litellm_gateway import LiteLLMGateway
from infrastructure.llm.ollama_manager import OllamaManager
from infrastructure.persistence.in_memory import InMemoryCostRepository
from shared.config import Settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("cache_hit_rate")


async def _run(
    model: str,
    calls: int,
    goal: str,
    verify_wiring: bool,
    pad_entries: int = 160,
) -> None:
    settings = Settings()
    if "claude" in model and not settings.has_anthropic:
        raise SystemExit("ANTHROPIC_API_KEY is required for Claude models.")
    if model.startswith("ollama/"):
        logger.warning(
            "Ollama does not surface cached_tokens — cache_hit_rate will be 0."
        )

    cost_repo = InMemoryCostRepository()
    cost_tracker = CostTracker(cost_repo)
    ollama = OllamaManager(settings)
    gateway = LiteLLMGateway(ollama, cost_tracker, settings)

    if verify_wiring:
        # Force the cached prefix above Anthropic's minimum (~1024 tokens for
        # Claude 4) by patching the planner's _SYSTEM_PROMPT module constant
        # with a padded variant. This proves the cache_control wiring works
        # end-to-end; do not run this in production.
        from infrastructure.fractal import llm_planner as _planner_mod

        pad = (
            "\n\n# Reference glossary (pad to reach Anthropic cache minimum):\n"
            + "\n".join(
                f"- term_{i}: a long stable definition used purely to inflate "
                f"the cached portion of the system prompt above the provider "
                f"minimum (~2048 tokens empirically for Claude 4) so cache "
                f"reads can be observed end-to-end."
                for i in range(pad_entries)
            )
        )
        original = _planner_mod._SYSTEM_PROMPT
        _planner_mod._SYSTEM_PROMPT = original + pad
        logger.info(
            "verify-wiring mode: padded _SYSTEM_PROMPT %d → %d chars",
            len(original),
            len(_planner_mod._SYSTEM_PROMPT),
        )

    planner = LLMPlanner(gateway, candidates_per_node=3, max_depth=3, model=model)

    print("\n=== TD-193 cache_hit_rate baseline ===")
    print(f"model: {model}")
    print(f"calls: {calls}")
    print(f"goal:  {goal!r}\n")

    for _ in range(calls):
        await planner.generate_candidates(goal=goal, context="", nesting_level=0)

    print(
        f"{'#':>3}  {'prompt':>7}  {'cached':>7}  {'completion':>10}  "
        f"{'cost_usd':>9}  hit"
    )
    print("-" * 56)
    cached_total = 0
    prompt_total = 0
    cost_total = 0.0
    for i, r in enumerate(cost_repo.records, start=1):
        hit = "YES" if r.cached_tokens > 0 else "no"
        print(
            f"{i:>3}  {r.prompt_tokens:>7}  {r.cached_tokens:>7}  "
            f"{r.completion_tokens:>10}  ${r.cost_usd:>7.5f}  {hit}"
        )
        cached_total += r.cached_tokens
        prompt_total += r.prompt_tokens
        cost_total += r.cost_usd

    rate = cached_total / prompt_total if prompt_total else 0.0
    print("-" * 56)
    print(
        f"cache_hit_rate = {rate:.3f}  "
        f"({cached_total}/{prompt_total} cached tokens)"
    )
    print(f"total_cost     = ${cost_total:.5f}")


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="claude-haiku-4-5-20251001")
    p.add_argument("--calls", type=int, default=5)
    p.add_argument(
        "--goal",
        default="Build a small REST API for a TODO list with CRUD endpoints",
    )
    p.add_argument(
        "--verify-wiring",
        action="store_true",
        help=(
            "Pad the SYSTEM prompt above Anthropic's ~1024-token minimum so "
            "cache hits are physically possible. Use only to prove the "
            "cache_control wiring works end-to-end; not a normal workload."
        ),
    )
    p.add_argument(
        "--pad-entries",
        type=int,
        default=160,
        help=(
            "Number of glossary entries appended to the SYSTEM prompt when "
            "--verify-wiring is set. ~225 chars/entry → 160 ≈ 8.4K tokens. "
            "Use to sweep cache thresholds."
        ),
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse()
    asyncio.run(
        _run(
            args.model,
            args.calls,
            args.goal,
            args.verify_wiring,
            args.pad_entries,
        )
    )
