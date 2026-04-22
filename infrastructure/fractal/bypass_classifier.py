"""FractalBypassClassifier — LLM intent analysis for SIMPLE task bypass.

TD-167: Determines whether a goal is truly SIMPLE and can skip fractal
decomposition entirely, delegating directly to the inner engine.

All classification goes through LLM intent analysis — no rule-based
shortcuts. The LLM understands nuance that regex patterns cannot.

Conservative design: uncertain → proceed with fractal (never false-positive).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from domain.ports.llm_gateway import LLMGateway
from domain.value_objects.task_complexity import TaskComplexity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stable system prompt (KV-cache friendly — never changes)
# ---------------------------------------------------------------------------
_CLASSIFY_SYSTEM = """\
You are a task complexity classifier. Analyze the user's goal and determine \
whether it can be completed in a SINGLE step or requires multi-step planning.

Respond with ONLY a JSON object (no other text):
{"complexity": "SIMPLE" | "MEDIUM" | "COMPLEX", "reason": "one sentence"}

Definitions:
SIMPLE = Answerable in ONE step with a single LLM call. No external tools, \
no research, no multi-step coordination needed.
  Examples: "What is 2+2?", "Write a fibonacci function in Python", \
"Explain what REST means", "Hello world in Go"

MEDIUM = Requires 2-3 coordinated steps, tool usage, or research.
  Examples: "Search for the latest AI news", "Build a function with unit tests", \
"Fix the login bug and add a regression test"

COMPLEX = Requires 4+ steps, multiple tools, architecture decisions, or deep \
investigation across many files.
  Examples: "Refactor the auth system to use OAuth2", "Build a full-stack app"

IMPORTANT: When uncertain, choose MEDIUM. It is safer to plan than to skip.\
"""


@dataclass(frozen=True)
class BypassDecision:
    """Result of the bypass classification."""

    bypass: bool
    complexity: TaskComplexity
    reason: str


def _extract_json_object(text: str) -> str:
    """Extract JSON object from LLM output that may contain think tags."""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # Try markdown code block first
    md = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if md:
        return md.group(1)
    # Find first JSON object
    obj = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if obj:
        return obj.group(0)
    return cleaned


class FractalBypassClassifier:
    """LLM-powered intent classifier for fractal bypass decisions.

    Every goal goes through LLM intent analysis — the model understands
    nuance that regex patterns cannot capture.
    """

    def __init__(
        self,
        llm: LLMGateway,
        model: str | None = None,
    ) -> None:
        self._llm = llm
        self._model = model

    async def should_bypass(self, goal: str) -> BypassDecision:
        """Determine if a goal should bypass fractal decomposition.

        Uses LLM intent analysis to classify the goal's complexity.
        Returns BypassDecision with bypass=True only for confirmed SIMPLE goals.
        """
        return await self._llm_classify(goal)

    async def _llm_classify(self, goal: str) -> BypassDecision:
        """Use LLM to classify goal complexity with semantic understanding."""
        try:
            messages = [
                {"role": "system", "content": _CLASSIFY_SYSTEM},
                {"role": "user", "content": goal},
            ]
            response = await self._llm.complete(
                messages,
                model=self._model,
                temperature=0.1,  # Low temperature for deterministic classification
                max_tokens=256,  # Short response expected
            )
            return self._parse_response(response.content)
        except Exception:
            logger.warning(
                "LLM bypass classification failed — defaulting to fractal",
                exc_info=True,
            )
            return BypassDecision(
                bypass=False,
                complexity=TaskComplexity.MEDIUM,
                reason="LLM classification failed, defaulting to fractal planning",
            )

    @staticmethod
    def _parse_response(content: str) -> BypassDecision:
        """Parse LLM classification response into a BypassDecision."""
        raw = _extract_json_object(content)
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Could not parse classification JSON: %s", raw[:200])
            return BypassDecision(
                bypass=False,
                complexity=TaskComplexity.MEDIUM,
                reason="Unparseable LLM response, defaulting to fractal",
            )

        complexity_str = str(data.get("complexity", "MEDIUM")).upper()
        reason = str(data.get("reason", "LLM classification"))

        if complexity_str == "SIMPLE":
            return BypassDecision(
                bypass=True,
                complexity=TaskComplexity.SIMPLE,
                reason=reason,
            )
        if complexity_str == "COMPLEX":
            return BypassDecision(
                bypass=False,
                complexity=TaskComplexity.COMPLEX,
                reason=reason,
            )
        # MEDIUM or anything else → don't bypass
        return BypassDecision(
            bypass=False,
            complexity=TaskComplexity.MEDIUM,
            reason=reason,
        )
