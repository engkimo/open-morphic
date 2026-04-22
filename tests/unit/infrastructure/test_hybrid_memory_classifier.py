"""Tests for HybridMemoryClassifier (Sprint 11.2)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from domain.ports.llm_gateway import LLMGateway, LLMResponse
from domain.value_objects.cognitive import CognitiveMemoryType
from infrastructure.cognitive.hybrid_memory_classifier import HybridMemoryClassifier


def _mock_llm(response_text: str = "SEMANTIC") -> LLMGateway:
    """Build a mock LLM gateway returning the given text."""
    mock = AsyncMock(spec=LLMGateway)
    mock.complete.return_value = LLMResponse(
        content=response_text,
        model="test-model",
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=0.001,
    )
    return mock


def _failing_llm() -> LLMGateway:
    """Build a mock LLM that raises on complete()."""
    mock = AsyncMock(spec=LLMGateway)
    mock.complete.side_effect = ConnectionError("LLM unavailable")
    return mock


class TestSyncClassify:
    """HybridMemoryClassifier.classify() — sync regex-only path."""

    def test_regex_procedural(self) -> None:
        classifier = HybridMemoryClassifier()
        mem_type, conf = classifier.classify("how to deploy the application")
        assert mem_type == CognitiveMemoryType.PROCEDURAL
        assert conf >= 0.5

    def test_regex_semantic(self) -> None:
        classifier = HybridMemoryClassifier()
        mem_type, conf = classifier.classify("uses PostgreSQL for storage")
        assert mem_type == CognitiveMemoryType.SEMANTIC

    def test_regex_working(self) -> None:
        classifier = HybridMemoryClassifier()
        mem_type, conf = classifier.classify("currently in progress")
        assert mem_type == CognitiveMemoryType.WORKING

    def test_regex_episodic_default(self) -> None:
        classifier = HybridMemoryClassifier()
        mem_type, conf = classifier.classify("decided to use Redis")
        assert mem_type == CognitiveMemoryType.EPISODIC

    def test_no_match_defaults_episodic(self) -> None:
        classifier = HybridMemoryClassifier()
        mem_type, conf = classifier.classify("xyz random text")
        assert mem_type == CognitiveMemoryType.EPISODIC
        assert conf == 0.3


class TestAsyncClassify:
    """HybridMemoryClassifier.classify_async() — hybrid regex + LLM."""

    @pytest.mark.anyio
    async def test_high_confidence_skips_llm(self) -> None:
        """When regex confidence >= threshold, LLM is not called."""
        llm = _mock_llm()
        classifier = HybridMemoryClassifier(llm_gateway=llm, confidence_threshold=0.5)
        mem_type, conf = await classifier.classify_async("how to deploy the app")
        assert mem_type == CognitiveMemoryType.PROCEDURAL
        llm.complete.assert_not_called()

    @pytest.mark.anyio
    async def test_low_confidence_triggers_llm(self) -> None:
        """When regex confidence < threshold, LLM is called."""
        llm = _mock_llm("SEMANTIC")
        classifier = HybridMemoryClassifier(llm_gateway=llm, confidence_threshold=0.5)
        # "xyz" has no regex match → confidence 0.3 < 0.5
        mem_type, conf = await classifier.classify_async("xyz random text")
        assert mem_type == CognitiveMemoryType.SEMANTIC
        assert conf >= 0.7
        llm.complete.assert_called_once()

    @pytest.mark.anyio
    async def test_llm_returns_procedural(self) -> None:
        llm = _mock_llm("PROCEDURAL")
        classifier = HybridMemoryClassifier(llm_gateway=llm, confidence_threshold=0.5)
        mem_type, _ = await classifier.classify_async("ambiguous content")
        assert mem_type == CognitiveMemoryType.PROCEDURAL

    @pytest.mark.anyio
    async def test_llm_returns_working(self) -> None:
        llm = _mock_llm("WORKING")
        classifier = HybridMemoryClassifier(llm_gateway=llm, confidence_threshold=0.5)
        mem_type, _ = await classifier.classify_async("ambiguous content")
        assert mem_type == CognitiveMemoryType.WORKING

    @pytest.mark.anyio
    async def test_llm_returns_episodic(self) -> None:
        llm = _mock_llm("EPISODIC")
        classifier = HybridMemoryClassifier(llm_gateway=llm, confidence_threshold=0.5)
        mem_type, _ = await classifier.classify_async("ambiguous content")
        assert mem_type == CognitiveMemoryType.EPISODIC

    @pytest.mark.anyio
    async def test_llm_unparseable_falls_back_to_regex(self) -> None:
        """If LLM returns garbage, regex result is kept."""
        llm = _mock_llm("I'm not sure, maybe something?")
        classifier = HybridMemoryClassifier(llm_gateway=llm, confidence_threshold=0.5)
        mem_type, conf = await classifier.classify_async("ambiguous content")
        assert mem_type == CognitiveMemoryType.EPISODIC
        assert conf == 0.3  # Regex default

    @pytest.mark.anyio
    async def test_llm_failure_graceful_degradation(self) -> None:
        """If LLM call fails, regex result is returned."""
        llm = _failing_llm()
        classifier = HybridMemoryClassifier(llm_gateway=llm, confidence_threshold=0.5)
        mem_type, conf = await classifier.classify_async("ambiguous content")
        assert mem_type == CognitiveMemoryType.EPISODIC
        assert conf == 0.3

    @pytest.mark.anyio
    async def test_no_llm_gateway_uses_regex_only(self) -> None:
        """Without LLM gateway, always uses regex."""
        classifier = HybridMemoryClassifier(llm_gateway=None, confidence_threshold=0.5)
        mem_type, conf = await classifier.classify_async("ambiguous content")
        assert mem_type == CognitiveMemoryType.EPISODIC
        assert conf == 0.3

    @pytest.mark.anyio
    async def test_confidence_boosted_by_llm(self) -> None:
        """LLM classification boosts confidence to at least 0.7."""
        llm = _mock_llm("SEMANTIC")
        classifier = HybridMemoryClassifier(llm_gateway=llm, confidence_threshold=0.5)
        _, conf = await classifier.classify_async("ambiguous content")
        assert conf >= 0.7


class TestParseLLMResponse:
    """HybridMemoryClassifier._parse_llm_response()."""

    def test_exact_match(self) -> None:
        result = HybridMemoryClassifier._parse_llm_response("EPISODIC")
        assert result == CognitiveMemoryType.EPISODIC

    def test_case_insensitive(self) -> None:
        result = HybridMemoryClassifier._parse_llm_response("semantic")
        assert result == CognitiveMemoryType.SEMANTIC

    def test_with_whitespace(self) -> None:
        result = HybridMemoryClassifier._parse_llm_response("  PROCEDURAL  ")
        assert result == CognitiveMemoryType.PROCEDURAL

    def test_embedded_in_text(self) -> None:
        text = "The answer is WORKING."
        result = HybridMemoryClassifier._parse_llm_response(text)
        assert result == CognitiveMemoryType.WORKING

    def test_garbage_returns_none(self) -> None:
        assert HybridMemoryClassifier._parse_llm_response("I don't know") is None

    def test_empty_returns_none(self) -> None:
        assert HybridMemoryClassifier._parse_llm_response("") is None
