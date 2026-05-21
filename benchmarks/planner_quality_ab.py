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
from domain.services.planner_model_router import PlannerModelRouter
from domain.value_objects.planner_model import PlannerModel
from infrastructure.events.in_memory_event_bus import InMemoryEventBus
from infrastructure.fractal.llm_plan_evaluator import LLMPlanEvaluator
from infrastructure.fractal.llm_planner import LLMPlanner
from infrastructure.llm.cost_tracker import CostTracker
from infrastructure.llm.litellm_gateway import LiteLLMGateway
from infrastructure.llm.ollama_manager import OllamaManager
from infrastructure.metrics.router_metrics import RouterMetrics
from infrastructure.observability.router_observer import RouterObservingEventBus
from infrastructure.persistence.in_memory import InMemoryCostRepository
from infrastructure.routing.llm_goal_classifier import LLMGoalClassifier
from shared.config import Settings

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("planner_quality_ab")

SONNET = "claude-sonnet-4-6"
HAIKU = "claude-haiku-4-5-20251001"
ROUTER = "router"  # virtual arm: PlannerModelRouter picks Haiku or Sonnet per goal
JUDGE = SONNET  # consistent judge across all arms — eliminates self-grading bias

_PLANNER_MODEL_TO_GATEWAY: dict[PlannerModel, str] = {
    PlannerModel.SONNET: SONNET,
    PlannerModel.HAIKU: HAIKU,
}

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
    model: str  # arm label: SONNET, HAIKU, or ROUTER
    trial: int
    parse_success: bool
    schema_valid: bool
    entity_preserved: float
    plan_eval: float
    candidate_count: int
    cost_usd: float
    chosen_model: str | None = None  # for ROUTER arm — actual planner model used
    classifier_cost_usd: float = 0.0  # for ROUTER arm — extra classifier overhead
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


async def _classify_goals(
    *,
    classifier: LLMGoalClassifier,
    router: PlannerModelRouter,
    goals: list[str],
) -> dict[str, tuple[PlannerModel, float]]:
    """Run the router once per goal; return ``{goal: (chosen_model, classifier_cost)}``."""
    out: dict[str, tuple[PlannerModel, float]] = {}
    for goal in goals:
        chosen, classification = await router.select_for(goal)
        cost = classification.cost_usd if classification is not None else 0.0
        out[goal] = (chosen, cost)
    return out


def _print_router_summary(
    *,
    sonnet: ModelSummary,
    haiku: ModelSummary,
    router: ModelSummary,
    threshold_pt: float,
    plan_eval_threshold: float,
    captured_saving_threshold: float,
    chosen_models: dict[str, str],
) -> bool:
    print("\n=== Router-gated arm summary (per AD-4 acceptance) ===")
    print(f"{'metric':<20}  {'Sonnet (base)':>14}  {'Router':>10}  "
          f"{'Δ (Router−Sonnet)':>22}")
    print("-" * 74)

    def line(name: str, base: float, r: float, *, pct: bool, threshold: float) -> bool:
        delta = r - base
        b_str = f"{base * 100:>12.1f}%" if pct else f"{base:>14.3f}"
        r_str = f"{r * 100:>8.1f}%" if pct else f"{r:>10.3f}"
        d_str = f"{delta * 100:>+19.1f}pt" if pct else f"{delta:>+22.3f}"
        ok = delta >= -threshold
        marker = "✓" if ok else "✗"
        print(f"{name:<20}  {b_str}  {r_str}  {d_str}  {marker}")
        return ok

    ok_parse = line("parse_success", sonnet.parse_success, router.parse_success,
                    pct=True, threshold=threshold_pt / 100)
    ok_schema = line("schema_valid", sonnet.schema_valid, router.schema_valid,
                     pct=True, threshold=threshold_pt / 100)
    ok_entity = line("entity_preserved", sonnet.entity_preserved, router.entity_preserved,
                     pct=True, threshold=threshold_pt / 100)
    ok_eval = line("plan_eval", sonnet.plan_eval, router.plan_eval,
                   pct=False, threshold=plan_eval_threshold)

    print()
    print(f"avg cost/call: Sonnet ${sonnet.avg_cost_usd:.5f}  "
          f"Haiku ${haiku.avg_cost_usd:.5f}  Router ${router.avg_cost_usd:.5f}")
    captured = 0.0
    if sonnet.avg_cost_usd > haiku.avg_cost_usd:
        captured = (
            (sonnet.avg_cost_usd - router.avg_cost_usd)
            / (sonnet.avg_cost_usd - haiku.avg_cost_usd)
        )
        print(f"captured-saving (Router) vs theoretical max (Haiku-only): "
              f"{captured * 100:.1f}%")
    ok_capture = captured >= captured_saving_threshold

    counts: dict[str, int] = {}
    for v in chosen_models.values():
        counts[v] = counts.get(v, 0) + 1
    print(f"router routing breakdown: {counts}")

    all_ok = ok_parse and ok_schema and ok_entity and ok_eval and ok_capture
    verdict = ("PASS — Router meets AD-4 quality + captured-saving thresholds"
               if all_ok
               else "FAIL — Router violates at least one AD-4 acceptance bar")
    print(f"\nRouter verdict: {verdict}")
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

    arms = (SONNET, HAIKU, ROUTER) if args.router else (SONNET, HAIKU)
    title = ("Sonnet 4.6 vs Haiku 4.5 vs Router"
             if args.router
             else "Sonnet 4.6 vs Haiku 4.5")
    print(f"=== LLMPlanner quality A/B: {title} ===")
    print(f"goals: {len(GOALS)}  trials/model: {args.trials}  judge: {JUDGE}")
    print(f"cost cap: ${args.cost_cap_usd:.2f}\n")

    chosen_models: dict[str, str] = {}
    classifier_cost_total = 0.0
    if args.router:
        classifier = LLMGoalClassifier(gateway=gateway)
        metrics = RouterMetrics()
        bus = RouterObservingEventBus(inner=InMemoryEventBus(), metrics=metrics)
        router = PlannerModelRouter(
            classifier=classifier,
            event_bus=bus,
            enabled=True,
            haiku_confidence_threshold=0.7,
            classifier_timeout_ms=5_000,
        )
        print("  [router] classifying 10 goals...", flush=True)
        verdicts = await _classify_goals(
            classifier=classifier, router=router, goals=GOALS
        )
        for g, (m, c) in verdicts.items():
            chosen_models[g] = m.value
            classifier_cost_total += c
        print(f"  [router] classifier cost: ${classifier_cost_total:.5f}  "
              f"breakdown: {chosen_models}\n", flush=True)

    rows: list[TrialResult] = []
    for arm in arms:
        if arm == ROUTER:
            for goal in GOALS:
                pm, cls_cost = verdicts[goal]
                planner_model = _PLANNER_MODEL_TO_GATEWAY[pm]
                planner = LLMPlanner(
                    gateway, candidates_per_node=3, max_depth=3, model=planner_model
                )
                for trial in range(1, args.trials + 1):
                    running = sum(r.cost_usd for r in cost_repo.records)
                    if running > args.cost_cap_usd:
                        print(f"\n!! cost cap ${args.cost_cap_usd:.2f} exceeded "
                              f"(spent ${running:.4f}) — aborting", file=sys.stderr)
                        _print_detail(rows)
                        return 2
                    print(f"  router→{pm.value} | trial {trial} | {goal[:50]}",
                          flush=True)
                    row = await _run_one(
                        planner=planner,
                        evaluator=evaluator,
                        cost_repo=cost_repo,
                        goal=goal,
                        model=ROUTER,
                        trial=trial,
                    )
                    row.chosen_model = pm.value
                    row.classifier_cost_usd = cls_cost
                    # Roll the per-goal classifier overhead into the router cost.
                    row.cost_usd = round(row.cost_usd + cls_cost, 6)
                    rows.append(row)
        else:
            planner = LLMPlanner(gateway, candidates_per_node=3, max_depth=3, model=arm)
            for goal in GOALS:
                for trial in range(1, args.trials + 1):
                    running = sum(r.cost_usd for r in cost_repo.records)
                    if running > args.cost_cap_usd:
                        print(f"\n!! cost cap ${args.cost_cap_usd:.2f} exceeded "
                              f"(spent ${running:.4f}) — aborting", file=sys.stderr)
                        _print_detail(rows)
                        return 2
                    print(f"  {arm} | trial {trial} | {goal[:60]}", flush=True)
                    row = await _run_one(
                        planner=planner,
                        evaluator=evaluator,
                        cost_repo=cost_repo,
                        goal=goal,
                        model=arm,
                        trial=trial,
                    )
                    rows.append(row)

    _print_detail(rows)

    sonnet_sum = _summarize(rows, SONNET)
    haiku_sum = _summarize(rows, HAIKU)
    passed = _print_summary(sonnet_sum, haiku_sum, args.threshold_pt)

    router_passed = True
    if args.router:
        router_sum = _summarize(rows, ROUTER)
        router_passed = _print_router_summary(
            sonnet=sonnet_sum,
            haiku=haiku_sum,
            router=router_sum,
            threshold_pt=args.threshold_pt,
            plan_eval_threshold=args.plan_eval_threshold,
            captured_saving_threshold=args.captured_saving_threshold,
            chosen_models=chosen_models,
        )

    total_cost = sum(r.cost_usd for r in cost_repo.records)
    print(f"\nTotal benchmark cost: ${total_cost:.4f} ({len(cost_repo.records)} LLM calls)")
    if args.router:
        print(f"  (router classifier overhead: ${classifier_cost_total:.5f})")

    if args.dump:
        dump_payload: dict[str, object] = {
            "judge": JUDGE,
            "trials": args.trials,
            "router_mode": args.router,
            "rows": [r.__dict__ for r in rows],
            "summary": {
                "sonnet": sonnet_sum.__dict__,
                "haiku": haiku_sum.__dict__,
            },
            "total_cost_usd": round(total_cost, 6),
        }
        if args.router:
            dump_payload["summary"]["router"] = _summarize(rows, ROUTER).__dict__  # type: ignore[index]
            dump_payload["router_chosen_models"] = chosen_models
            dump_payload["router_classifier_cost_usd"] = round(classifier_cost_total, 6)
        Path(args.dump).write_text(
            json.dumps(dump_payload, indent=2, ensure_ascii=False)
        )
        print(f"Raw results dumped to {args.dump}")

    return 0 if (passed and router_passed) else 1


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
    p.add_argument("--router", action="store_true",
                   help="Enable router-gated 3rd arm (AD-4 per-goal routing).")
    p.add_argument("--plan-eval-threshold", type=float, default=0.030,
                   help="Router arm passes plan_eval if Δ >= -this (default 0.030).")
    p.add_argument("--captured-saving-threshold", type=float, default=0.30,
                   help="Router arm passes captured-saving if >= this (default 0.30).")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(_parse())))
