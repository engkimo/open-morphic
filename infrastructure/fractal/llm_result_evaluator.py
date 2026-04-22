"""LLMResultEvaluator — ResultEvaluatorPort implementation powered by LLM gateway.

Sprint 15.4: Post-execution quality assessment (Gate ②). Evaluates node
execution output on accuracy, validity, and goal_alignment. Uses cheapest
available model (Ollama preferred, AD-3). The ResultEvalDecisionMaker
converts raw scores into OK/RETRY/REPLAN decisions.

Cost strategy: Ollama first ($0), cloud models optional.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime

from domain.entities.fractal_engine import PlanNode, ResultEvaluation
from domain.ports.llm_gateway import LLMGateway
from domain.ports.result_evaluator import ResultEvaluatorPort
from domain.services.result_eval_decision_maker import ResultEvalDecisionMaker
from domain.value_objects.fractal_engine import ResultEvalDecision
from domain.value_objects.output_requirement import OutputRequirement

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stable system prompt prefix (KV-cache friendly — never changes)
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are a result evaluator for a fractal execution engine. Given a task \
node, its goal, and the execution result, evaluate the quality on three axes:

1. accuracy — Is the result factually correct and free of hallucination?
2. validity — Is the output well-formed, complete, and usable?
3. goal_alignment — Does the result actually achieve what the goal requires?

Return a JSON object with these fields:
  "accuracy"       (number) — score between 0.0 and 1.0
  "validity"       (number) — score between 0.0 and 1.0
  "goal_alignment" (number) — score between 0.0 and 1.0
  "feedback"       (string) — brief explanation of your assessment

Return ONLY the JSON object. No commentary outside the object.\
"""


class LLMResultEvaluator(ResultEvaluatorPort):
    """LLM-powered result evaluation — Gate ② of the fractal engine."""

    def __init__(
        self,
        llm: LLMGateway,
        model: str | None = None,
        ok_threshold: float = 0.7,
        retry_threshold: float = 0.4,
        axis_weights: dict[str, float] | None = None,
    ) -> None:
        self._llm = llm
        self._model = model
        self._ok_threshold = ok_threshold
        self._retry_threshold = retry_threshold
        self._axis_weights = axis_weights

    # ------------------------------------------------------------------
    # ResultEvaluatorPort implementation
    # ------------------------------------------------------------------

    async def evaluate(
        self,
        node: PlanNode,
        goal: str,
        result: str,
    ) -> ResultEvaluation:
        """Evaluate the execution result of a plan node."""
        try:
            messages = self._build_messages(node, goal, result)
            response = await self._llm.complete(
                messages,
                model=self._model,
                temperature=0.2,
                max_tokens=1024,
            )
            raw_eval = self._parse_evaluation(response.content, node.id)
            return ResultEvalDecisionMaker.decide(
                raw_eval,
                ok_threshold=self._ok_threshold,
                retry_threshold=self._retry_threshold,
                axis_weights=self._axis_weights,
            )
        except Exception:
            logger.exception(
                "Result evaluation failed for node=%s — using fallback",
                node.id,
            )
            return self._fallback_evaluation(node.id)

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_messages(
        node: PlanNode,
        goal: str,
        result: str,
    ) -> list[dict]:
        """Build chat messages with stable prefix and dynamic node/goal/result."""
        result_preview = result[:2000] if len(result) > 2000 else result

        # Output-aware evaluation: add requirement-specific instructions
        output_hint = ""
        req = node.output_requirement
        if req == OutputRequirement.FILE_ARTIFACT:
            output_hint = (
                "\n\nIMPORTANT: This goal requires producing a FILE ARTIFACT "
                "(not just text). When evaluating goal_alignment, check:\n"
                "- Was an actual file created (via fs_write or similar tool)?\n"
                "- Does the result reference a concrete file path?\n"
                "- If only text DESCRIBING a file was generated (without "
                "creating it), goal_alignment should be LOW (< 0.3)."
            )
        elif req == OutputRequirement.CODE_ARTIFACT:
            output_hint = (
                "\n\nIMPORTANT: This goal requires producing a CODE ARTIFACT. "
                "When evaluating goal_alignment, check:\n"
                "- Was actual code written to a file?\n"
                "- If only pseudo-code or description was generated without "
                "creating a real file, goal_alignment should be LOW (< 0.3)."
            )
        elif req == OutputRequirement.DATA_ARTIFACT:
            output_hint = (
                "\n\nIMPORTANT: This goal requires DATA retrieval or analysis. "
                "When evaluating goal_alignment, check:\n"
                "- Was real data fetched from external sources?\n"
                "- If only hypothetical or placeholder data was generated, "
                "goal_alignment should be LOW (< 0.3)."
            )

        user_content = (
            f"Goal: {goal}\n\n"
            f"Task node: {node.description}\n"
            f"Nesting level: {node.nesting_level}\n"
            f"Terminal: {node.is_terminal}\n\n"
            f"Execution result:\n{result_preview}"
            f"{output_hint}"
        )
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_evaluation(content: str, node_id: str) -> ResultEvaluation:
        """Parse LLM JSON response into ResultEvaluation (without decision)."""
        data = _extract_json_object(content)

        accuracy = _clamp(float(data.get("accuracy", 0.5)))
        validity = _clamp(float(data.get("validity", 0.5)))
        goal_alignment = _clamp(float(data.get("goal_alignment", 0.5)))
        feedback = str(data.get("feedback", ""))

        return ResultEvaluation(
            node_id=node_id,
            accuracy=round(accuracy, 4),
            validity=round(validity, 4),
            goal_alignment=round(goal_alignment, 4),
            overall_score=0.0,  # DecisionMaker will compute
            decision=ResultEvalDecision.OK,  # DecisionMaker will overwrite
            feedback=feedback,
            timestamp=datetime.now(),
        )

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------

    def _fallback_evaluation(self, node_id: str) -> ResultEvaluation:
        """Conservative fallback when LLM evaluation fails."""
        raw = ResultEvaluation(
            node_id=node_id,
            accuracy=0.5,
            validity=0.5,
            goal_alignment=0.5,
            overall_score=0.0,
            decision=ResultEvalDecision.OK,  # DecisionMaker will overwrite
            feedback="Fallback evaluation — LLM unavailable",
            timestamp=datetime.now(),
        )
        return ResultEvalDecisionMaker.decide(
            raw,
            ok_threshold=self._ok_threshold,
            retry_threshold=self._retry_threshold,
            axis_weights=self._axis_weights,
        )


def _extract_json_object(content: str) -> dict:
    """Extract a JSON object from LLM output (may contain think tags or markdown)."""
    text = content.strip()
    # Strip <think>...</think> blocks (qwen3 reasoning)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # Try ```json ... ``` code blocks
    md_match = re.search(r"```(?:json)?\s*(\{.*?})\s*```", text, re.DOTALL)
    if md_match:
        return json.loads(md_match.group(1))
    # Try direct JSON object
    obj_match = re.search(r"\{.*}", text, re.DOTALL)
    if obj_match:
        return json.loads(obj_match.group(0))
    # Last resort: try the whole text
    return json.loads(text)


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp a value to [lo, hi]."""
    return max(lo, min(hi, value))
