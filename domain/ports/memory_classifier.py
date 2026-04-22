"""MemoryClassifierPort — abstraction for text → CognitiveMemoryType classification.

Domain defines WHAT it needs. Infrastructure provides HOW (regex, LLM, hybrid, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.value_objects.cognitive import CognitiveMemoryType


class MemoryClassifierPort(ABC):
    """Port for classifying free-form text into a cognitive memory type."""

    @abstractmethod
    def classify(self, content: str) -> tuple[CognitiveMemoryType, float]:
        """Classify text and return (memory_type, confidence).

        Returns:
            Tuple of (CognitiveMemoryType, confidence_score).
            Confidence is in [0.0, 1.0].
        """
        ...
