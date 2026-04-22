"""Tests for EngineCostCalculator — pure domain service."""

from __future__ import annotations

from domain.services.engine_cost_calculator import EngineCostCalculator, UsageCost


class TestCalculate:
    """EngineCostCalculator.calculate()"""

    def test_none_usage_returns_zero(self):
        assert EngineCostCalculator.calculate("claude-sonnet-4-6", None) == 0.0

    def test_empty_usage_returns_zero(self):
        assert EngineCostCalculator.calculate("claude-sonnet-4-6", {}) == 0.0

    def test_zero_tokens_returns_zero(self):
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        assert EngineCostCalculator.calculate("claude-sonnet-4-6", usage) == 0.0

    def test_claude_sonnet_pricing(self):
        # 1000 input + 500 output → ($3/1M * 1000) + ($15/1M * 500)
        usage = {"prompt_tokens": 1000, "completion_tokens": 500}
        cost = EngineCostCalculator.calculate("claude-sonnet-4-6", usage)
        expected = (1000 / 1_000_000) * 3.0 + (500 / 1_000_000) * 15.0
        assert cost == round(expected, 6)

    def test_claude_opus_pricing(self):
        usage = {"prompt_tokens": 1000, "completion_tokens": 500}
        cost = EngineCostCalculator.calculate("claude-opus-4-6", usage)
        expected = (1000 / 1_000_000) * 15.0 + (500 / 1_000_000) * 75.0
        assert cost == round(expected, 6)

    def test_o4_mini_pricing(self):
        usage = {"prompt_tokens": 10000, "completion_tokens": 5000}
        cost = EngineCostCalculator.calculate("o4-mini", usage)
        expected = (10000 / 1_000_000) * 1.10 + (5000 / 1_000_000) * 4.40
        assert cost == round(expected, 6)

    def test_gpt4o_pricing(self):
        usage = {"prompt_tokens": 10000, "completion_tokens": 5000}
        cost = EngineCostCalculator.calculate("gpt-4o", usage)
        expected = (10000 / 1_000_000) * 2.50 + (5000 / 1_000_000) * 10.0
        assert cost == round(expected, 6)

    def test_gemini_pricing(self):
        usage = {"prompt_tokens": 10000, "completion_tokens": 5000}
        cost = EngineCostCalculator.calculate("gemini/gemini-2.5-pro", usage)
        expected = (10000 / 1_000_000) * 1.25 + (5000 / 1_000_000) * 10.0
        assert cost == round(expected, 6)

    def test_ollama_always_free(self):
        usage = {"prompt_tokens": 100000, "completion_tokens": 50000}
        assert EngineCostCalculator.calculate("ollama/qwen3:8b", usage) == 0.0

    def test_none_model_uses_default(self):
        usage = {"prompt_tokens": 1000, "completion_tokens": 500}
        cost = EngineCostCalculator.calculate(None, usage)
        # Default is medium tier (3.0, 15.0)
        expected = (1000 / 1_000_000) * 3.0 + (500 / 1_000_000) * 15.0
        assert cost == round(expected, 6)

    def test_unknown_model_uses_default(self):
        usage = {"prompt_tokens": 1000, "completion_tokens": 500}
        cost = EngineCostCalculator.calculate("some-future-model", usage)
        expected = (1000 / 1_000_000) * 3.0 + (500 / 1_000_000) * 15.0
        assert cost == round(expected, 6)

    def test_input_tokens_alias(self):
        """Some APIs return input_tokens/output_tokens instead."""
        usage = {"input_tokens": 1000, "output_tokens": 500}
        cost = EngineCostCalculator.calculate("claude-sonnet-4-6", usage)
        assert cost > 0.0

    def test_substring_model_match(self):
        """Model strings with date suffixes should still match."""
        usage = {"prompt_tokens": 1000, "completion_tokens": 500}
        cost = EngineCostCalculator.calculate("claude-sonnet-4-6-20260301", usage)
        expected = (1000 / 1_000_000) * 3.0 + (500 / 1_000_000) * 15.0
        assert cost == round(expected, 6)

    def test_non_numeric_tokens_coerced(self):
        usage = {"prompt_tokens": "1000", "completion_tokens": "500"}
        cost = EngineCostCalculator.calculate("claude-sonnet-4-6", usage)
        assert cost > 0.0

    def test_invalid_tokens_return_zero(self):
        usage = {"prompt_tokens": "bad", "completion_tokens": None}
        assert EngineCostCalculator.calculate("claude-sonnet-4-6", usage) == 0.0


class TestCalculateDetailed:
    """EngineCostCalculator.calculate_detailed()"""

    def test_returns_usage_cost(self):
        usage = {"prompt_tokens": 1000, "completion_tokens": 500}
        result = EngineCostCalculator.calculate_detailed("claude-sonnet-4-6", usage)
        assert isinstance(result, UsageCost)
        assert result.input_tokens == 1000
        assert result.output_tokens == 500
        assert result.input_cost_usd > 0
        assert result.output_cost_usd > 0
        assert result.total_cost_usd == round(result.input_cost_usd + result.output_cost_usd, 6)

    def test_none_usage(self):
        result = EngineCostCalculator.calculate_detailed("claude-sonnet-4-6", None)
        assert result.total_cost_usd == 0.0
        assert result.input_tokens == 0

    def test_consistency_with_calculate(self):
        usage = {"prompt_tokens": 5000, "completion_tokens": 2000}
        simple = EngineCostCalculator.calculate("o4-mini", usage)
        detailed = EngineCostCalculator.calculate_detailed("o4-mini", usage)
        assert simple == detailed.total_cost_usd


class TestEstimateFromDuration:
    """EngineCostCalculator.estimate_from_duration()"""

    def test_basic_estimate(self):
        # $3/hr for 60 seconds = $0.05
        cost = EngineCostCalculator.estimate_from_duration(3.0, 60.0)
        assert cost == round(3.0 / 3600.0 * 60.0, 6)

    def test_zero_rate(self):
        assert EngineCostCalculator.estimate_from_duration(0.0, 60.0) == 0.0

    def test_zero_duration(self):
        assert EngineCostCalculator.estimate_from_duration(3.0, 0.0) == 0.0

    def test_negative_values(self):
        assert EngineCostCalculator.estimate_from_duration(-1.0, 60.0) == 0.0
