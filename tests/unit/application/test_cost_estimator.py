"""Tests for CostEstimator — Sprint 2-C."""

from __future__ import annotations

import pytest

from application.use_cases.cost_estimator import CostEstimator, MODEL_COST_TABLE


class TestCostEstimatorLocalModels:
    def test_ollama_always_free(self) -> None:
        est = CostEstimator()
        results = est.estimate(["task1", "task2"], model="ollama/qwen3:8b")
        assert all(r.estimated_cost_usd == 0.0 for r in results)

    def test_ollama_any_model_free(self) -> None:
        est = CostEstimator()
        results = est.estimate(["task1"], model="ollama/custom:latest")
        assert results[0].estimated_cost_usd == 0.0

    def test_ollama_total_zero(self) -> None:
        est = CostEstimator()
        total = est.estimate_total(["a", "b", "c"], model="ollama/qwen3-coder:30b")
        assert total == 0.0

    def test_local_within_any_budget(self) -> None:
        est = CostEstimator()
        assert est.is_within_budget(["a", "b"], "ollama/qwen3:8b", budget_usd=0.0)


class TestCostEstimatorCloudModels:
    def test_claude_sonnet_costs(self) -> None:
        est = CostEstimator()
        results = est.estimate(["analyze code"], model="claude-sonnet-4-6")
        assert results[0].estimated_cost_usd > 0
        assert results[0].model == "claude-sonnet-4-6"

    def test_claude_opus_costs_more(self) -> None:
        est = CostEstimator()
        sonnet = est.estimate_total(["task"], model="claude-sonnet-4-6")
        opus = est.estimate_total(["task"], model="claude-opus-4-6")
        assert opus > sonnet

    def test_unknown_model_uses_default_pricing(self) -> None:
        est = CostEstimator()
        results = est.estimate(["task"], model="unknown-model-v99")
        assert results[0].estimated_cost_usd > 0  # Uses default 3.0/MTok

    def test_haiku_cheaper_than_sonnet(self) -> None:
        est = CostEstimator()
        haiku = est.estimate_total(["task"], model="claude-haiku-4-5-20251001")
        sonnet = est.estimate_total(["task"], model="claude-sonnet-4-6")
        assert haiku < sonnet


class TestCostEstimatorTokenHeuristic:
    def test_minimum_tokens(self) -> None:
        est = CostEstimator()
        results = est.estimate(["x"], model="claude-sonnet-4-6", tokens_per_subtask=1000)
        assert results[0].estimated_tokens >= 1000

    def test_longer_description_more_tokens(self) -> None:
        est = CostEstimator()
        short = est.estimate(["hi"], model="claude-sonnet-4-6")
        long_desc = "Implement a comprehensive authentication system with JWT tokens and refresh tokens"
        long = est.estimate([long_desc], model="claude-sonnet-4-6")
        assert long[0].estimated_tokens >= short[0].estimated_tokens

    def test_multiple_subtasks(self) -> None:
        est = CostEstimator()
        results = est.estimate(["a", "b", "c", "d", "e"], model="claude-sonnet-4-6")
        assert len(results) == 5


class TestCostEstimatorBudget:
    def test_within_budget_true(self) -> None:
        est = CostEstimator()
        assert est.is_within_budget(["task"], "claude-sonnet-4-6", budget_usd=1.0)

    def test_exceeds_budget_false(self) -> None:
        est = CostEstimator()
        assert not est.is_within_budget(
            ["t"] * 1000, "claude-opus-4-6", budget_usd=0.001
        )

    def test_custom_cost_table(self) -> None:
        custom_table = {"my-model": 100.0}
        est = CostEstimator(cost_table=custom_table)
        results = est.estimate(["task"], model="my-model")
        assert results[0].estimated_cost_usd > 0
