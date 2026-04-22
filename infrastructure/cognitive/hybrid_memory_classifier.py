"""Hybrid memory classifier — regex-first with LLM fallback.

Implements :class:`MemoryClassifierPort`.
Uses the existing regex-based :class:`MemoryClassifier` as the fast path.
Falls back to LLM classification when regex confidence is low.
"""

from __future__ import annotations

import logging

from domain.ports.llm_gateway import LLMGateway
from domain.ports.memory_classifier import MemoryClassifierPort
from domain.services.memory_classifier import MemoryClassifier
from domain.value_objects.cognitive import CognitiveMemoryType

logger = logging.getLogger(__name__)

# Prompt for LLM classification — kept minimal for cost efficiency
_CLASSIFY_PROMPT = """\
Classify the following text into exactly one category:
- EPISODIC: events, actions taken (decided, created, failed, completed)
- SEMANTIC: facts, knowledge (uses, requires, is a, supports)
- PROCEDURAL: strategies, how-to (how to, steps, best practice, always)
- WORKING: current state (currently, in progress, blocked, pending)

Text: {text}

Reply with ONLY the category name (EPISODIC, SEMANTIC, PROCEDURAL, or WORKING)."""


class HybridMemoryClassifier(MemoryClassifierPort):
    """Regex-first classifier with LLM fallback for low-confidence cases.

    Strategy:
        1. Run regex-based MemoryClassifier (fast, free)
        2. If confidence < threshold → ask LLM (slower, may cost $)
        3. If LLM unavailable → return regex result (graceful degradation)
    """

    def __init__(
        self,
        llm_gateway: LLMGateway | None = None,
        confidence_threshold: float = 0.5,
    ) -> None:
        self._llm = llm_gateway
        self._threshold = confidence_threshold

    def classify(self, content: str) -> tuple[CognitiveMemoryType, float]:
        """Classify synchronously using regex only.

        The sync interface satisfies the port contract.
        Use :meth:`classify_async` for the full hybrid path.
        """
        return MemoryClassifier.classify_with_confidence(content)

    async def classify_async(self, content: str) -> tuple[CognitiveMemoryType, float]:
        """Full hybrid classification: regex-first, LLM fallback."""
        regex_type, regex_conf = MemoryClassifier.classify_with_confidence(content)

        if regex_conf >= self._threshold:
            return regex_type, regex_conf

        if self._llm is None:
            return regex_type, regex_conf

        # LLM fallback
        try:
            response = await self._llm.complete(
                messages=[
                    {"role": "user", "content": _CLASSIFY_PROMPT.format(text=content)},
                ],
                temperature=0.0,
                max_tokens=32,
            )
            llm_type = self._parse_llm_response(response.content)
            if llm_type is not None:
                return llm_type, max(0.7, regex_conf)
        except Exception:
            logger.debug("LLM fallback failed for memory classification, using regex result")

        return regex_type, regex_conf

    @staticmethod
    def _parse_llm_response(text: str) -> CognitiveMemoryType | None:
        """Parse LLM response to CognitiveMemoryType."""
        cleaned = text.strip().upper()
        mapping = {
            "EPISODIC": CognitiveMemoryType.EPISODIC,
            "SEMANTIC": CognitiveMemoryType.SEMANTIC,
            "PROCEDURAL": CognitiveMemoryType.PROCEDURAL,
            "WORKING": CognitiveMemoryType.WORKING,
        }
        for key, mem_type in mapping.items():
            if key in cleaned:
                return mem_type
        return None
