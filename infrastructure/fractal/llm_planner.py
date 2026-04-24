"""LLMPlanner — PlannerPort implementation powered by an LLM gateway.

Sprint 15.2: Takes a goal at any nesting level and produces candidate nodes
(visible + conditional fallback). Domain-agnostic — knowledge lives in the
generated plan, not the engine.
"""

from __future__ import annotations

import json
import logging
import re

from domain.entities.fractal_engine import CandidateNode, PlanNode
from domain.ports.fractal_learning_repository import FractalLearningRepository
from domain.ports.llm_gateway import LLMGateway
from domain.ports.planner import PlannerPort
from domain.value_objects.fractal_engine import NodeState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stable system prompt prefix (KV-cache friendly — TD-190).
#
# This string is the byte-identical system message for every planner call,
# regardless of direction, nesting level, parent context, candidates_per_node,
# or learning data. All per-request values live in the user message so the
# prefix-keyed KV cache hits on every subsequent call.
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are a fractal execution planner. Given a goal, generate an ordered \
sequence of candidate execution steps as a JSON array.

Each element must be a JSON object with these fields:
  "description"      (string)  — action-oriented step description (start with a verb).
  "is_terminal"      (boolean) — true if the step is an atomic action (no sub-steps).
  "score"            (number)  — confidence score between 0.0 and 1.0.
  "condition"        (string|null) — null for primary (visible) steps; \
a natural-language condition string for conditional fallback steps.
  "input_artifacts"  (object)  — key-value pairs of expected input artifacts (can be empty {}).
  "output_artifacts" (object)  — key-value pairs of produced output artifacts (can be empty {}).

Planning direction (set per request via the user message):
- FORWARD: start from the current state and work toward the goal. \
List steps in execution order.
- BACKWARD: start from the goal state and work back to the initial conditions. \
List steps in reverse order.

Rules:
- Every description MUST start with an action verb (e.g. "Fetch", "Parse", "Generate").
- Each description MUST preserve the specific entities, topics, proper nouns, \
and search terms from the original goal. Do NOT abstract them away.
  BAD:  "Search for information"
  GOOD: "Search for '氷川神社 歴史' (Hikawa Shrine history)"
  BAD:  "Create a presentation"
  GOOD: "Create a PPTX slide file about Hikawa Shrine history"
- If the goal requires producing a file (slide, report, image, etc.), the \
step description MUST name the concrete file format or tool.
- Scores reflect your confidence that the step is necessary and correct.
- Primary steps have condition=null. Fallback steps have a condition describing when to activate.
- Return ONLY the JSON array. No commentary outside the array.\
"""


def _extract_json(content: str) -> str:
    """Extract JSON array from LLM output that may contain think tags or markdown."""
    text = content.strip()
    # Strip <think>...</think> blocks (qwen3 reasoning)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # Extract from ```json ... ``` code blocks
    md_match = re.search(r"```(?:json)?\s*(\[.*?])\s*```", text, re.DOTALL)
    if md_match:
        return md_match.group(1)
    # Find first JSON array
    arr_match = re.search(r"\[.*]", text, re.DOTALL)
    if arr_match:
        return arr_match.group(0)
    return text


class LLMPlanner(PlannerPort):
    """Generate candidate node sequences from a goal via LLM."""

    def __init__(
        self,
        llm: LLMGateway,
        candidates_per_node: int = 3,
        max_depth: int = 3,
        model: str | None = None,
        learning_repo: FractalLearningRepository | None = None,
    ) -> None:
        self._llm = llm
        self._candidates_per_node = candidates_per_node
        self._max_depth = max_depth
        self._model = model
        self._learning_repo = learning_repo

    # ------------------------------------------------------------------
    # PlannerPort implementation
    # ------------------------------------------------------------------

    async def generate_candidates(
        self,
        goal: str,
        context: str,
        nesting_level: int,
        direction: str = "forward",
    ) -> list[CandidateNode]:
        """Generate candidate nodes for the given goal."""
        try:
            learning_context = await self._build_learning_context(goal)
            messages = self._build_messages(
                goal, context, nesting_level, direction, learning_context
            )
            response = await self._llm.complete(
                messages,
                model=self._model,
                temperature=0.3,
                max_tokens=2048,
            )
            candidates = self._parse_candidates(response.content, nesting_level)
            if not candidates:
                logger.warning("Empty candidates after parsing — returning fallback")
                return [self._fallback_candidate(goal, nesting_level)]
            logger.info(
                "Generated %d candidate(s) for goal=%r at level=%d",
                len(candidates),
                goal[:60],
                nesting_level,
            )
            return candidates
        except Exception:
            logger.exception("LLM planner failed — returning fallback")
            return [self._fallback_candidate(goal, nesting_level)]

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        goal: str,
        context: str,
        nesting_level: int,
        direction: str,
        learning_context: str = "",
    ) -> list[dict]:
        """Build chat messages with a byte-stable system prefix (TD-190).

        Per Manus 5原則 / KV-cache stability: every per-request value
        (direction, nesting level, candidates count, parent context,
        learning data, goal) lives in the user message. The system prompt
        is the same string for every call regardless of caller — this is
        what lets the KV cache hit on the prompt prefix.
        """
        direction_token = "BACKWARD" if direction == "backward" else "FORWARD"

        user_parts: list[str] = []
        if learning_context:
            user_parts.append(learning_context)

        user_parts.append(
            f"Direction: {direction_token}\n"
            f"Nesting level: {nesting_level} (0=top-level scenario)\n"
            f"Generate approximately {self._candidates_per_node} candidate steps."
        )
        if context:
            user_parts.append(f"Parent context:\n{context}")

        user_parts.append(f"Goal: {goal}")

        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": "\n\n".join(user_parts)},
        ]

    # ------------------------------------------------------------------
    # Learning context
    # ------------------------------------------------------------------

    async def _build_learning_context(self, goal: str) -> str:
        """Query learning repo and format as concise context for the planner."""
        if self._learning_repo is None:
            return ""

        try:
            error_patterns = await self._learning_repo.find_error_patterns_by_goal(goal)
            successful_paths = await self._learning_repo.find_successful_paths(goal)
        except Exception:
            logger.warning("Failed to query learning repo", exc_info=True)
            return ""

        # Sort by relevance, cap to avoid context bloat
        error_patterns.sort(key=lambda p: p.occurrence_count, reverse=True)
        successful_paths.sort(key=lambda p: p.usage_count, reverse=True)
        errors = error_patterns[:5]
        paths = successful_paths[:3]

        if not errors and not paths:
            logger.info("No learning data found for goal=%r", goal[:60])
            return ""

        parts: list[str] = []

        logger.info(
            "Learning data found: %d error patterns, %d successful paths for goal=%r",
            len(errors),
            len(paths),
            goal[:60],
        )

        if errors:
            parts.append("Known failure patterns (AVOID these approaches):")
            for ep in errors:
                parts.append(
                    f'  - "{ep.node_description}" failed with: '
                    f"{ep.error_message} (seen {ep.occurrence_count}x)"
                )

        if paths:
            parts.append("Proven successful approaches (PREFER these):")
            for sp in paths:
                steps = " -> ".join(sp.node_descriptions)
                cost = f" (cost: ${sp.total_cost_usd:.4f})" if sp.total_cost_usd > 0 else ""
                parts.append(f"  - [{steps}]{cost} (used {sp.usage_count}x)")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_candidates(self, content: str, nesting_level: int) -> list[CandidateNode]:
        """Parse LLM JSON response into CandidateNode list."""
        raw_json = _extract_json(content)
        items: list[dict] = json.loads(raw_json)

        candidates: list[CandidateNode] = []
        force_terminal = nesting_level >= self._max_depth - 1

        for item in items:
            desc = (item.get("description") or "").strip()
            if not desc:
                continue

            is_terminal = bool(item.get("is_terminal", False))
            if force_terminal:
                is_terminal = True

            score = float(item.get("score", 0.5))
            score = max(0.0, min(1.0, score))

            condition = item.get("condition")
            state = NodeState.CONDITIONAL if condition is not None else NodeState.VISIBLE

            node = PlanNode(
                description=desc,
                nesting_level=nesting_level,
                is_terminal=is_terminal,
                input_artifacts=item.get("input_artifacts") or {},
                output_artifacts=item.get("output_artifacts") or {},
            )

            candidates.append(
                CandidateNode(
                    node=node,
                    state=state,
                    score=score,
                    activation_condition=condition if state == NodeState.CONDITIONAL else None,
                )
            )

        return candidates

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _fallback_candidate(goal: str, nesting_level: int) -> CandidateNode:
        """Return a single VISIBLE terminal node as a safe fallback."""
        node = PlanNode(
            description=goal,
            nesting_level=nesting_level,
            is_terminal=True,
        )
        return CandidateNode(
            node=node,
            state=NodeState.VISIBLE,
            score=1.0,
        )
