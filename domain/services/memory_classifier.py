"""Memory classifier — categorises text into CognitiveMemoryType.

Pure static domain service.  No external dependencies.
"""

from __future__ import annotations

import re

from domain.value_objects.cognitive import CognitiveMemoryType

# Pre-compiled patterns — priority order: PROCEDURAL > SEMANTIC > WORKING > EPISODIC
_PROCEDURAL_RE = re.compile(
    r"\b(?:how\s+to|steps?\s+to|strateg(?:y|ies)|best\s+practice|always|never|avoid|prefer)\b",
    re.IGNORECASE,
)

_SEMANTIC_RE = re.compile(
    r"\b(?:uses|requires|depends\s+on|version|is\s+a|configured\s+with|supports)\b",
    re.IGNORECASE,
)

_WORKING_RE = re.compile(
    r"\b(?:currently|in\s+progress|next\s+step|blocked|pending|remaining)\b",
    re.IGNORECASE,
)

_EPISODIC_RE = re.compile(
    r"\b(?:decided|created|failed|error|completed|installed|fixed)\b",
    re.IGNORECASE,
)

_PATTERNS: list[tuple[re.Pattern[str], CognitiveMemoryType]] = [
    (_PROCEDURAL_RE, CognitiveMemoryType.PROCEDURAL),
    (_SEMANTIC_RE, CognitiveMemoryType.SEMANTIC),
    (_WORKING_RE, CognitiveMemoryType.WORKING),
    (_EPISODIC_RE, CognitiveMemoryType.EPISODIC),
]


class MemoryClassifier:
    """Classify free-form text into a :class:`CognitiveMemoryType`."""

    @staticmethod
    def classify(text: str) -> CognitiveMemoryType:
        """Return the first matching memory type, or EPISODIC as default."""
        for pattern, memory_type in _PATTERNS:
            if pattern.search(text):
                return memory_type
        return CognitiveMemoryType.EPISODIC

    @staticmethod
    def classify_with_confidence(
        text: str,
    ) -> tuple[CognitiveMemoryType, float]:
        """Classify and return a confidence score based on keyword density.

        Confidence = min(0.3 + hit_count * 0.2, 0.9).
        If no pattern matches, returns (EPISODIC, 0.3).
        """
        best_type = CognitiveMemoryType.EPISODIC
        best_hits = 0

        for pattern, memory_type in _PATTERNS:
            hits = len(pattern.findall(text))
            if hits > best_hits:
                best_hits = hits
                best_type = memory_type

        confidence = min(0.3 + best_hits * 0.2, 0.9)
        return best_type, confidence
