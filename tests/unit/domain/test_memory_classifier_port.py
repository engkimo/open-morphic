"""Tests for MemoryClassifierPort ABC (Sprint 11.2)."""

from __future__ import annotations

import pytest

from domain.ports.memory_classifier import MemoryClassifierPort
from domain.value_objects.cognitive import CognitiveMemoryType


class ConcreteClassifier(MemoryClassifierPort):
    """Minimal concrete implementation for testing the ABC contract."""

    def classify(self, content: str) -> tuple[CognitiveMemoryType, float]:
        return CognitiveMemoryType.EPISODIC, 0.5


class TestMemoryClassifierPort:
    """MemoryClassifierPort interface tests."""

    def test_is_abstract(self) -> None:
        """Cannot instantiate ABC directly."""
        with pytest.raises(TypeError):
            MemoryClassifierPort()  # type: ignore[abstract]

    def test_concrete_implements_classify(self) -> None:
        """Concrete implementation satisfies the port contract."""
        classifier = ConcreteClassifier()
        mem_type, conf = classifier.classify("some text")
        assert isinstance(mem_type, CognitiveMemoryType)
        assert isinstance(conf, float)

    def test_returns_tuple(self) -> None:
        """classify() returns a (type, confidence) tuple."""
        classifier = ConcreteClassifier()
        result = classifier.classify("test content")
        assert len(result) == 2
        assert result[0] == CognitiveMemoryType.EPISODIC
        assert result[1] == 0.5
