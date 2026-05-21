"""Tests for shared classifier prompt + parser (T050 RED).

Covers:
- clean JSON → GoalClassification
- JSON with `<think>...</think>` prefix (qwen3 habit) stripped
- JSON inside ```json ... ``` fences extracted
- malformed JSON → `ClassificationParseError`
- invalid `model` enum value → `ClassificationParseError`
- out-of-range confidence → `ClassificationParseError`
- SYSTEM_PROMPT is a non-empty constant (byte-identical across calls)
"""

from __future__ import annotations

import pytest

from domain.value_objects.planner_model import PlannerModel
from infrastructure.routing._prompts import (
    SYSTEM_PROMPT,
    ClassificationParseError,
    parse_classification,
)


class TestSystemPrompt:
    def test_is_non_empty_string(self) -> None:
        assert isinstance(SYSTEM_PROMPT, str)
        assert len(SYSTEM_PROMPT) > 100

    def test_identity_across_calls(self) -> None:
        from infrastructure.routing import _prompts as p1
        from infrastructure.routing import _prompts as p2

        assert p1.SYSTEM_PROMPT is p2.SYSTEM_PROMPT


class TestParseHappyPath:
    def test_clean_json(self) -> None:
        raw = '{"model": "haiku", "confidence": 0.92, "reason": "generic English"}'
        result = parse_classification(raw, latency_ms=120, cost_usd=0.0003)

        assert result.model is PlannerModel.HAIKU
        assert result.confidence == 0.92
        assert result.reason == "generic English"
        assert result.latency_ms == 120
        assert result.cost_usd == 0.0003

    def test_sonnet_value_parses(self) -> None:
        raw = '{"model": "sonnet", "confidence": 0.81, "reason": "Japanese present"}'
        result = parse_classification(raw, latency_ms=200, cost_usd=0.0)
        assert result.model is PlannerModel.SONNET

    def test_strips_think_block(self) -> None:
        raw = (
            "<think>The goal is in English and generic.</think>\n"
            '{"model": "haiku", "confidence": 0.88, "reason": "english generic"}'
        )
        result = parse_classification(raw, latency_ms=300, cost_usd=0.0)
        assert result.model is PlannerModel.HAIKU
        assert result.confidence == 0.88

    def test_strips_json_fence(self) -> None:
        raw = (
            "```json\n"
            '{"model": "sonnet", "confidence": 0.91, "reason": "non-ascii"}\n'
            "```"
        )
        result = parse_classification(raw, latency_ms=150, cost_usd=0.0001)
        assert result.model is PlannerModel.SONNET

    def test_extracts_first_object_from_noisy_output(self) -> None:
        raw = (
            "Sure, here is the JSON you asked for:\n"
            '{"model": "haiku", "confidence": 0.75, "reason": "generic"}\n'
            "Hope this helps!"
        )
        result = parse_classification(raw, latency_ms=110, cost_usd=0.0)
        assert result.model is PlannerModel.HAIKU


class TestParseErrorPath:
    def test_malformed_json_raises(self) -> None:
        with pytest.raises(ClassificationParseError):
            parse_classification("not json at all", latency_ms=10, cost_usd=0.0)

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ClassificationParseError):
            parse_classification("", latency_ms=10, cost_usd=0.0)

    def test_invalid_model_enum_raises(self) -> None:
        raw = '{"model": "gpt-4", "confidence": 0.9, "reason": "x"}'
        with pytest.raises(ClassificationParseError):
            parse_classification(raw, latency_ms=10, cost_usd=0.0)

    def test_confidence_above_one_raises(self) -> None:
        raw = '{"model": "haiku", "confidence": 1.5, "reason": "x"}'
        with pytest.raises(ClassificationParseError):
            parse_classification(raw, latency_ms=10, cost_usd=0.0)

    def test_confidence_negative_raises(self) -> None:
        raw = '{"model": "haiku", "confidence": -0.1, "reason": "x"}'
        with pytest.raises(ClassificationParseError):
            parse_classification(raw, latency_ms=10, cost_usd=0.0)

    def test_missing_required_field_raises(self) -> None:
        raw = '{"model": "haiku", "confidence": 0.9}'
        with pytest.raises(ClassificationParseError):
            parse_classification(raw, latency_ms=10, cost_usd=0.0)

    def test_long_reason_is_truncated_not_rejected(self) -> None:
        long_reason = "x" * 500
        raw = f'{{"model": "haiku", "confidence": 0.9, "reason": "{long_reason}"}}'
        result = parse_classification(raw, latency_ms=10, cost_usd=0.0)
        assert len(result.reason) <= 200
