"""LLMPlanner quality A/B: Haiku 4.5 vs Sonnet 4.6.

Quantifies plan quality on four axes across a fixed goal set so we can
decide whether the 66.7% per-call cost saving projected by
``benchmarks.planner_cost_simulation`` is paid for by acceptable plan
quality.

Axes (per goal × model × trial):
  1. ``parse_success`` — planner returned a non-fallback candidate list
     (i.e. ``_parse_candidates`` did not collapse to the goal-echo fallback).
  2. ``schema_valid`` — every candidate has a non-empty action-verb
     description, ``0.0 ≤ score ≤ 1.0``, dict artifacts. (Pydantic already
     enforces types; this catches degenerate-but-valid output like a single
     "TODO" node.)
  3. ``entity_preserved`` — fraction of distinctive tokens from the goal
     (quoted strings, proper nouns, digits, katakana/kanji compounds) that
     appear in the concatenated plan-node descriptions. Rule-of-thumb proxy
     for the prompt rule "preserve specific entities — do NOT abstract them
     away".
  4. ``plan_eval`` — ``LLMPlanEvaluator`` overall_score, judged by Sonnet
     4.6 for both arms (consistent judge eliminates self-grading bias).

Pass criterion: Haiku 4.5 within −5pt of Sonnet 4.6 on every axis.

Safety: aborts if cumulative cost exceeds ``--cost-cap-usd`` (default $1.00).

Usage:
    uv run --extra dev python -m benchmarks.planner_quality_ab
    uv run --extra dev python -m benchmarks.planner_quality_ab --trials 2

Outputs a per-(goal,model,trial) detail table and a per-model summary with
deltas. Optional ``--dump <path>`` writes the raw plan JSON per call so
reviewers can re-check the entity-preservation heuristic by hand.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from domain.entities.fractal_engine import CandidateNode, ExecutionPlan, PlanNode
from infrastructure.fractal.llm_plan_evaluator import LLMPlanEvaluator
from infrastructure.fractal.llm_planner import LLMPlanner
from infrastructure.llm.cost_tracker import CostTracker
from infrastructure.llm.litellm_gateway import LiteLLMGateway
from infrastructure.llm.ollama_manager import OllamaManager
from infrastructure.persistence.in_memory import InMemoryCostRepository
from shared.config import Settings

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("planner_quality_ab")

SONNET = "claude-sonnet-4-6"
HAIKU = "claude-haiku-4-5-20251001"
JUDGE = SONNET  # consistent judge across both arms — eliminates self-grading bias

# 10 goals chosen to span: simple/complex, EN/JA, text/file output, technical/everyday.
GOALS: list[str] = [
    "Build a small REST API for a TODO list with CRUD endpoints",
    "Summarize the difference between TCP and UDP in two paragraphs",
    "Create a PPTX slide file about Hikawa Shrine history",
    "氷川神社の歴史についてPPTXスライドを作成",
    "Generate a Python script that sorts a CSV file by the 'date' column",
    "東京から京都への新幹線の最安ルートを調査して表にまとめる",
    "Write unit tests for a function called calculate_compound_interest",
    "Plan a 3-day trip to Kyoto for a vegetarian traveler in November",
    "Convert a markdown file to PDF using pandoc and verify the output",
    "Implement Dijkstra's shortest-path algorithm in Rust with tests",
]


# Patterns that pick out distinctive tokens worth preserving.
_QUOTED = re.compile(r"['\"]([^'\"]+)['\"]")
_PROPER = re.compile(r"\b[A-Z][A-Za-z0-9_]{2,}\b")  # ProperCase / acronyms ≥3 chars
_DIGIT = re.compile(r"\b\d+\b")
# Katakana run or kanji run length ≥ 2.
_JP = re.compile(r"[\u30A0-\u30FF]{2,}|[\u4E00-\u9FFF]{2,}")


def _distinctive_tokens(goal: str) -> set[str]:
    """Extract distinctive tokens worth preserving in the plan."""
    tokens: set[str] = set()
    tokens.update(m.group(1) for m in _QUOTED.finditer(goal))
    tokens.update(_PROPER.findall(goal))
    tokens.update(_DIGIT.findall(goal))
    tokens.update(_JP.findall(goal))
    # Drop trivially short tokens.
    return {t for t in tokens if len(t) >= 2}


def _entity_preservation(goal: str, descriptions: list[str]) -> float:
    """Fraction of distinctive goal tokens present in the plan descriptions."""
    tokens = _distinctive_tokens(goal)
    if not tokens:
        return 1.0  # no entities to preserve
    body = " ".join(descriptions).lower()
    hits = sum(1 for t in tokens if t.lower() in body)
    return hits / len(tokens)


def _schema_valid(candidates: list[CandidateNode]) -> bool:
    """True if all candidates have non-empty action-style descriptions and a sane score."""
    if not candidates:
        return False
    for c in candidates:
        desc = c.node.description.strip()
        if not desc:
            return False
        if not (0.0 <= c.score <= 1.0):
            return False
    return True


def _is_fallback(candidates: list[CandidateNode], goal: str) -> bool:
    """LLMPlanner returns ``[fallback_candidate(goal)]`` on parse failure — detect it."""
    if len(candidates) != 1:
        return False
    desc = candidates[0].node.description.strip()
    # Fallback description is the goal verbatim (or "Achieve: <goal>" depending on version).
    return desc == goal or desc.endswith(goal)


def _candidates_to_plan(candidates: list[CandidateNode], goal: str) -> ExecutionPlan:
    """Convert candidates → ExecutionPlan so the evaluator can score it."""
    visible: list[PlanNode] = [c.node for c in candidates if c.state.name == "VISIBLE"]
    if not visible:
        visible = [c.node for c in candidates]
    return ExecutionPlan(
        goal=goal,
        nesting_level=0,
        visible_nodes=visible,
        candidate_space=candidates,
    )


@dataclass
class TrialResult:
    goal: str
    model: str
    trial: int
    parse_success: bool
    schema_valid: bool
    entity_preserved: float
    plan_eval: float
    candidate_count: int
    cost_usd: float
    plan_descriptions: list[str] = field(default_factory=list)


@dataclass
class ModelSummary:
    model: str
    parse_success: float
    schema_valid: float
    entity_preserved: float
    plan_eval: float
    avg_cost_usd: float
    n: int


async def _run_one(
    *,
    planner: LLMPlanner,
    evaluator: LLMPlanEvaluator,
    cost_repo: InMemoryCostRepository,
    goal: str,
    model: str,
    trial: int,
) -> TrialResult:
    pre = len(cost_repo.records)
    candidates = await planner.generate_candidates(goal=goal, context="", nesting_level=0)
    descriptions = [c.node.description for c in candidates]
    parse_success = not _is_fallback(candidates, goal)
    schema_valid = _schema_valid(candidates)
    entity = _entity_preservation(goal, descriptions)

    plan = _candidates_to_plan(candidates, goal)
    evaluation = await evaluator.evaluate(plan, goal)

    post_records = cost_repo.records[pre:]
    cost = sum(r.cost_usd for r in post_records)

    return TrialResult(
        goal=goal,
        model=model,
        trial=trial,
        parse_success=parse_success,
        schema_valid=schema_valid,
        entity_preserved=round(entity, 4),
        plan_eval=round(evaluation.overall_score, 4),
        candidate_count=len(candidates),
        cost_usd=round(cost, 6),
        plan_descriptions=descriptions,
    )


def _summarize(rows: list[TrialResult], model: str) -> ModelSummary:
    sub = [r for r in rows if r.model == model]
    n = len(sub)
    if n == 0:
        return ModelSummary(model, 0, 0, 0, 0, 0, 0)
    return ModelSummary(
        model=model,
        parse_success=sum(1 for r in sub if r.parse_success) / n,
        schema_valid=sum(1 for r in sub if r.schema_valid) / n,
        entity_preserved=sum(r.entity_preserved for r in sub) / n,
        plan_eval=sum(r.plan_eval for r in sub) / n,
        avg_cost_usd=sum(r.cost_usd for r in sub) / n,
        n=n,
    )


def _print_detail(rows: list[TrialResult]) -> None:
    print(
        f"\n{'#':>3}  {'model':<28}  {'trial':>5}  {'parse':>5}  "
        f"{'schema':>6}  {'entity':>6}  {'eval':>6}  {'cost':>9}  goal"
    )
    print("-" * 110)
    for i, r in enumerate(rows, 1):
        print(
            f"{i:>3}  {r.model:<28}  {r.trial:>5}  "
            f"{'YES' if r.parse_success else 'no':>5}  "
            f"{'YES' if r.schema_valid else 'no':>6}  "
            f"{r.entity_preserved:>6.2f}  {r.plan_eval:>6.3f}  "
            f"${r.cost_usd:>7.5f}  {r.goal[:48]}"
        )


def _print_summary(sonnet: ModelSummary, haiku: ModelSummary, threshold_pt: float) -> bool:
    print("\n=== Per-model summary (mean across all goals × trials) ===")
    print(f"{'metric':<20}  {'Sonnet 4.6':>12}  {'Haiku 4.5':>12}  {'Δ (Haiku − Sonnet)':>22}")
    print("-" * 74)

    def line(name: str, s: float, h: float, *, pct: bool) -> tuple[float, bool]:
        delta = h - s
        s_str = f"{s * 100:>10.1f}%" if pct else f"{s:>12.3f}"
        h_str = f"{h * 100:>10.1f}%" if pct else f"{h:>12.3f}"
        d_str = f"{delta * 100:>+19.1f}pt" if pct else f"{delta:>+22.3f}"
        threshold = threshold_pt / 100 if pct else threshold_pt / 100
        ok = delta >= -threshold
        marker = "✓" if ok else "✗"
        print(f"{name:<20}  {s_str}  {h_str}  {d_str}  {marker}")
        return delta, ok

    _, ok_parse = line(
        "parse_success", sonnet.parse_success, haiku.parse_success, pct=True
    )
    _, ok_schema = line(
        "schema_valid", sonnet.schema_valid, haiku.schema_valid, pct=True
    )
    _, ok_entity = line(
        "entity_preserved", sonnet.entity_preserved, haiku.entity_preserved, pct=True
    )
    _, ok_eval = line("plan_eval", sonnet.plan_eval, haiku.plan_eval, pct=False)

    print()
    print(f"avg cost/call: Sonnet ${sonnet.avg_cost_usd:.5f}  Haiku ${haiku.avg_cost_usd:.5f}")
    if sonnet.avg_cost_usd > 0:
        save = (sonnet.avg_cost_usd - haiku.avg_cost_usd) / sonnet.avg_cost_usd * 100
        print(f"cost saving (Haiku vs Sonnet): {save:.1f}%")

    all_ok = ok_parse and ok_schema and ok_entity and ok_eval
    if all_ok:
        verdict = f"PASS — Haiku within −{threshold_pt:.0f}pt on every axis"
    else:
        verdict = (
            f"FAIL — Haiku regresses beyond −{threshold_pt:.0f}pt threshold "
            "on at least one axis"
        )
    print(f"\nVerdict: {verdict}")
    return all_ok


async def _main(args: argparse.Namespace) -> int:
    settings = Settings()
    if not settings.has_anthropic:
        raise SystemExit("ANTHROPIC_API_KEY is required for both arms.")

    cost_repo = InMemoryCostRepository()
    cost_tracker = CostTracker(cost_repo)
    ollama = OllamaManager(settings)
    gateway = LiteLLMGateway(ollama, cost_tracker, settings)

    evaluator = LLMPlanEvaluator(gateway, models=[JUDGE])

    print("=== LLMPlanner quality A/B: Sonnet 4.6 vs Haiku 4.5 ===")
    print(f"goals: {len(GOALS)}  trials/model: {args.trials}  judge: {JUDGE}")
    print(f"cost cap: ${args.cost_cap_usd:.2f}\n")

    rows: list[TrialResult] = []
    for model in (SONNET, HAIKU):
        planner = LLMPlanner(gateway, candidates_per_node=3, max_depth=3, model=model)
        for goal in GOALS:
            for trial in range(1, args.trials + 1):
                running = sum(r.cost_usd for r in cost_repo.records)
                if running > args.cost_cap_usd:
                    print(f"\n!! cost cap ${args.cost_cap_usd:.2f} exceeded "
                          f"(spent ${running:.4f}) — aborting", file=sys.stderr)
                    _print_detail(rows)
                    return 2
                print(f"  {model} | trial {trial} | {goal[:60]}", flush=True)
                row = await _run_one(
                    planner=planner,
                    evaluator=evaluator,
                    cost_repo=cost_repo,
                    goal=goal,
                    model=model,
                    trial=trial,
                )
                rows.append(row)

    _print_detail(rows)

    sonnet_sum = _summarize(rows, SONNET)
    haiku_sum = _summarize(rows, HAIKU)
    passed = _print_summary(sonnet_sum, haiku_sum, args.threshold_pt)

    total_cost = sum(r.cost_usd for r in cost_repo.records)
    print(f"\nTotal benchmark cost: ${total_cost:.4f} ({len(cost_repo.records)} LLM calls)")

    if args.dump:
        Path(args.dump).write_text(
            json.dumps(
                {
                    "judge": JUDGE,
                    "trials": args.trials,
                    "rows": [r.__dict__ for r in rows],
                    "summary": {
                        "sonnet": sonnet_sum.__dict__,
                        "haiku": haiku_sum.__dict__,
                    },
                    "total_cost_usd": round(total_cost, 6),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        print(f"Raw results dumped to {args.dump}")

    return 0 if passed else 1


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trials", type=int, default=3,
                   help="Trials per (goal, model). Default 3.")
    p.add_argument("--cost-cap-usd", type=float, default=1.00,
                   help="Hard abort if cumulative LLM cost exceeds this.")
    p.add_argument("--threshold-pt", type=float, default=5.0,
                   help="Pass if Haiku is within this many points of Sonnet on every axis.")
    p.add_argument("--dump", type=str, default=None,
                   help="Optional path to dump raw JSON results.")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(_parse())))
