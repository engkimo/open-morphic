"""LLMReflectionEvaluator — ReflectionEvaluatorPort implementation.

Sprint 35 (TD-163): After all visible nodes execute, asks the LLM:
"Given the goal and completed work, is the goal fully addressed?
 If not, what specific aspects are missing?"

Cost strategy: Ollama first ($0), cloud models optional.
KV-cache: Stable system prompt prefix, dynamic content in user message.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime

from domain.entities.fractal_engine import PlanNode
from domain.entities.reflection import ReflectionResult
from domain.ports.llm_gateway import LLMGateway
from domain.ports.reflection_evaluator import ReflectionEvaluatorPort
from domain.value_objects.status import SubTaskStatus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stable system prompt prefix (KV-cache friendly — never changes)
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are a reflection evaluator for a fractal execution engine. After a set \
of execution nodes completes, you assess whether the original goal has been \
fully addressed.

Analyze the completed work and determine:
1. Is the goal FULLY satisfied by the completed nodes?
2. If NOT, what specific aspects are MISSING?
3. For each missing aspect, suggest a concrete action-oriented task description.

Return a JSON object with these fields:
  "satisfied"    (boolean) — true if goal is fully addressed
  "missing"      (array of strings) — aspects not yet covered (empty if satisfied)
  "suggestions"  (array of strings) — action-verb descriptions for new nodes \
(empty if satisfied, max 3)
  "confidence"   (number) — confidence in assessment, 0.0 to 1.0
  "feedback"     (string) — brief explanation

Return ONLY the JSON object. No commentary outside the object.\
"""


class LLMReflectionEvaluator(ReflectionEvaluatorPort):
    """LLM-powered reflection — assesses plan completeness after execution."""

    def __init__(
        self,
        llm: LLMGateway,
        model: str | None = None,
        max_suggestions: int = 3,
    ) -> None:
        self._llm = llm
        self._model = model
        self._max_suggestions = max_suggestions

    async def reflect(
        self,
        goal: str,
        completed_nodes: list[PlanNode],
        nesting_level: int,
    ) -> ReflectionResult:
        """Evaluate whether completed nodes fully satisfy the goal."""
        plan_id = str(uuid.uuid4())[:8]

        try:
            messages = self._build_messages(goal, completed_nodes, nesting_level)
            response = await self._llm.complete(
                messages,
                model=self._model,
                temperature=0.3,
                max_tokens=1024,
            )
            return self._parse_response(response.content, plan_id)
        except Exception:
            logger.exception("Reflection evaluation failed — returning satisfied fallback")
            return ReflectionResult(
                plan_id=plan_id,
                is_satisfied=True,
                confidence=0.3,
                feedback="Fallback — reflection LLM unavailable",
            )

    @staticmethod
    def _build_messages(
        goal: str,
        completed_nodes: list[PlanNode],
        nesting_level: int,
    ) -> list[dict]:
        """Build chat messages with stable prefix and dynamic completed work."""
        node_summaries: list[str] = []
        for i, node in enumerate(completed_nodes, 1):
            raw = node.status
            status = raw.value if isinstance(raw, SubTaskStatus) else str(raw)
            result_preview = (node.result or "")[:300]
            error_text = f" | Error: {node.error}" if node.error else ""
            node_summaries.append(
                f"{i}. [{status}] {node.description}\n"
                f"   Result: {result_preview}{error_text}"
            )

        user_content = (
            f"Goal: {goal}\n\n"
            f"Nesting level: {nesting_level}\n"
            f"Completed nodes ({len(completed_nodes)}):\n"
            + "\n".join(node_summaries)
        )
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    def _parse_response(self, content: str, plan_id: str) -> ReflectionResult:
        """Parse LLM JSON response into ReflectionResult."""
        data = _extract_json_object(content)

        satisfied = bool(data.get("satisfied", True))
        missing = [str(m) for m in data.get("missing", []) if m]
        suggestions = [str(s) for s in data.get("suggestions", []) if s]
        confidence = _clamp(float(data.get("confidence", 0.5)))
        feedback = str(data.get("feedback", ""))

        # Cap suggestions
        suggestions = suggestions[: self._max_suggestions]

        return ReflectionResult(
            plan_id=plan_id,
            is_satisfied=satisfied,
            missing_aspects=missing,
            suggested_descriptions=suggestions,
            confidence=round(confidence, 4),
            feedback=feedback,
            timestamp=datetime.now(),
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
    return json.loads(text)


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))
