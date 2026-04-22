"""Tests for ReflectionResult entity and NestingDepthController reflection guard.

Sprint 35 (TD-163): Living Fractal — reflection-driven dynamic node spawning.
"""

from __future__ import annotations

import pytest

from domain.entities.reflection import ReflectionResult
from domain.services.nesting_depth_controller import NestingDepthController

# ---------------------------------------------------------------------------
# ReflectionResult entity
# ---------------------------------------------------------------------------


class TestReflectionResult:
    def test_satisfied_defaults(self) -> None:
        r = ReflectionResult(plan_id="p1")
        assert r.is_satisfied is True
        assert r.missing_aspects == []
        assert r.suggested_descriptions == []
        assert r.confidence == 1.0
        assert r.spawn_count == 0

    def test_unsatisfied_with_suggestions(self) -> None:
        r = ReflectionResult(
            plan_id="p1",
            is_satisfied=False,
            missing_aspects=["data validation", "error handling"],
            suggested_descriptions=[
                "Validate input data format",
                "Add error handling for edge cases",
            ],
            confidence=0.8,
            feedback="Missing validation and error handling steps",
        )
        assert not r.is_satisfied
        assert r.spawn_count == 2
        assert len(r.missing_aspects) == 2
        assert r.confidence == 0.8

    def test_spawn_count_zero_when_satisfied(self) -> None:
        r = ReflectionResult(
            plan_id="p1",
            is_satisfied=True,
            suggested_descriptions=["this should be ignored"],
        )
        assert r.spawn_count == 0

    def test_confidence_clamped(self) -> None:
        with pytest.raises(ValueError):
            ReflectionResult(plan_id="p1", confidence=1.5)

    def test_plan_id_required(self) -> None:
        with pytest.raises(ValueError):
            ReflectionResult(plan_id="")


# ---------------------------------------------------------------------------
# NestingDepthController.check_reflection_allowed
# ---------------------------------------------------------------------------


class TestReflectionGuard:
    def test_allowed_first_round(self) -> None:
        allowed, reason = NestingDepthController.check_reflection_allowed(
            reflection_rounds=0,
            max_reflection_rounds=2,
            total_nodes=3,
            max_total_nodes=20,
        )
        assert allowed is True
        assert reason == "reflection_allowed"

    def test_blocked_max_rounds(self) -> None:
        allowed, reason = NestingDepthController.check_reflection_allowed(
            reflection_rounds=2,
            max_reflection_rounds=2,
            total_nodes=5,
            max_total_nodes=20,
        )
        assert allowed is False
        assert reason == "max_reflection_rounds_reached"

    def test_blocked_max_nodes(self) -> None:
        allowed, reason = NestingDepthController.check_reflection_allowed(
            reflection_rounds=0,
            max_reflection_rounds=2,
            total_nodes=20,
            max_total_nodes=20,
        )
        assert allowed is False
        assert reason == "max_total_nodes_reached"

    def test_blocked_budget_exhausted(self) -> None:
        allowed, reason = NestingDepthController.check_reflection_allowed(
            reflection_rounds=0,
            max_reflection_rounds=2,
            total_nodes=3,
            max_total_nodes=20,
            accumulated_cost_usd=5.0,
            budget_usd=5.0,
        )
        assert allowed is False
        assert reason == "budget_exhausted"

    def test_allowed_when_budget_zero_means_unlimited(self) -> None:
        allowed, reason = NestingDepthController.check_reflection_allowed(
            reflection_rounds=1,
            max_reflection_rounds=2,
            total_nodes=10,
            max_total_nodes=20,
            accumulated_cost_usd=100.0,
            budget_usd=0.0,
        )
        assert allowed is True
        assert reason == "reflection_allowed"
