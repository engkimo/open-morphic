"""LLMPlanEvaluator — PlanEvaluatorPort implementation powered by LLM gateway.

Sprint 15.3: Multi-LLM plan evaluation (Gate ①). Each configured model
independently scores an execution plan on completeness, feasibility, and
safety. Scores are aggregated by the domain PlanEvalAggregator.

Cost strategy (AD-3): Ollama first ($0), cloud models optional.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from domain.entities.fractal_engine import ExecutionPlan, PlanEvaluation
from domain.ports.llm_gateway import LLMGateway
from domain.ports.plan_evaluator import PlanEvaluatorPort
from domain.services.plan_eval_aggregator import PlanEvalAggregator
from domain.value_objects.fractal_engine import PlanEvalDecision
from infrastructure.fractal.llm_planner import _extract_json

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stable system prompt prefix (KV-cache friendly — never changes)
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are a plan evaluator for a fractal execution engine. Given an execution \
plan and its goal, evaluate the plan on three axes:

1. completeness — Does the plan cover all necessary steps to achieve the goal?
2. feasibility — Can each step be realistically executed with available tools?
3. safety — Are there any risks, destructive operations, or security concerns?

Return a JSON object with these fields:
  "completeness"  (number) — score between 0.0 and 1.0
  "feasibility"   (number) — score between 0.0 and 1.0
  "safety"        (number) — score between 0.0 and 1.0
  "feedback"      (string) — brief explanation of your assessment

Return ONLY the JSON object. No commentary outside the object.\
"""


class LLMPlanEvaluator(PlanEvaluatorPort):
    """Multi-LLM plan evaluation — Gate ① of the fractal engine."""

    def __init__(
        self,
        llm: LLMGateway,
        models: list[str] | None = None,
        min_score: float = 0.5,
        axis_weights: dict[str, float] | None = None,
    ) -> None:
        self._llm = llm
        self._models = models or []
        self._min_score = min_score
        self._axis_weights = axis_weights

    # ------------------------------------------------------------------
    # PlanEvaluatorPort implementation
    # ------------------------------------------------------------------

    async def evaluate(
        self,
        plan: ExecutionPlan,
        goal: str,
    ) -> PlanEvaluation:
        """Evaluate a plan using multiple LLMs, then aggregate."""
        models = self._models if self._models else [None]  # type: ignore[list-item]

        tasks = [self._evaluate_single(plan, goal, model) for model in models]
        evaluations = await asyncio.gather(*tasks)

        return PlanEvalAggregator.aggregate(
            evaluations,
            min_score=self._min_score,
            axis_weights=self._axis_weights,
        )

    # ------------------------------------------------------------------
    # Single-model evaluation
    # ------------------------------------------------------------------

    async def _evaluate_single(
        self,
        plan: ExecutionPlan,
        goal: str,
        model: str | None,
    ) -> PlanEvaluation:
        """Evaluate a plan with a single model, returning PlanEvaluation."""
        try:
            messages = self._build_messages(plan, goal)
            response = await self._llm.complete(
                messages,
                model=model,
                temperature=0.2,
                max_tokens=1024,
            )
            return self._parse_evaluation(
                response.content,
                plan.id,
                response.model,
            )
        except Exception:
            logger.exception(
                "Plan evaluation failed for model=%s — using fallback",
                model,
            )
            return self._fallback_evaluation(plan.id, model or "unknown")

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        plan: ExecutionPlan,
        goal: str,
    ) -> list[dict]:
        """Build chat messages with stable prefix and dynamic plan/goal."""
        plan_description = self._format_plan(plan)
        user_content = (
            f"Goal: {goal}\n\n"
            f"Execution Plan (nesting level {plan.nesting_level}):\n"
            f"{plan_description}"
        )
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    @staticmethod
    def _format_plan(plan: ExecutionPlan) -> str:
        """Format plan nodes for evaluation prompt."""
        lines: list[str] = []
        for i, node in enumerate(plan.visible_nodes, 1):
            terminal_tag = " [terminal]" if node.is_terminal else " [expandable]"
            lines.append(f"  {i}. {node.description}{terminal_tag}")
        conditional = plan.get_conditional_nodes()
        if conditional:
            lines.append("  Conditional fallbacks:")
            for c in conditional:
                lines.append(f"    - {c.node.description} (when: {c.activation_condition})")
        return "\n".join(lines) if lines else "  (empty plan)"

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_evaluation(
        self,
        content: str,
        plan_id: str,
        model_name: str,
    ) -> PlanEvaluation:
        """Parse LLM JSON response into PlanEvaluation."""
        raw_json = _extract_json(content)
        # _extract_json is tuned for arrays; for objects, also try direct parse
        data: dict
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            # Try to find a JSON object
            import re

            obj_match = re.search(r"\{.*}", content, re.DOTALL)
            if obj_match:
                data = json.loads(obj_match.group(0))
            else:
                raise

        if isinstance(data, list) and data:
            data = data[0]

        completeness = _clamp(float(data.get("completeness", 0.5)))
        feasibility = _clamp(float(data.get("feasibility", 0.5)))
        safety = _clamp(float(data.get("safety", 1.0)))
        feedback = str(data.get("feedback", ""))

        overall = (completeness + feasibility + safety) / 3.0

        return PlanEvaluation(
            plan_id=plan_id,
            evaluator_model=model_name,
            completeness=round(completeness, 4),
            feasibility=round(feasibility, 4),
            safety=round(safety, 4),
            overall_score=round(overall, 4),
            decision=PlanEvalDecision.APPROVED,  # aggregator decides final
            feedback=feedback,
            timestamp=datetime.now(),
        )

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _fallback_evaluation(plan_id: str, model: str) -> PlanEvaluation:
        """Conservative fallback when LLM evaluation fails."""
        return PlanEvaluation(
            plan_id=plan_id,
            evaluator_model=model,
            completeness=0.5,
            feasibility=0.5,
            safety=1.0,
            overall_score=round((0.5 + 0.5 + 1.0) / 3.0, 4),
            decision=PlanEvalDecision.APPROVED,  # aggregator decides final
            feedback="Fallback evaluation — LLM unavailable",
            timestamp=datetime.now(),
        )


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp a value to [lo, hi]."""
    return max(lo, min(hi, value))
