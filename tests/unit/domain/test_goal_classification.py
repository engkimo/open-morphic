"""Tests for GoalClassification VO (T011 RED)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.value_objects.goal_classification import GoalClassification
from domain.value_objects.planner_model import PlannerModel


def _base(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "model": PlannerModel.HAIKU,
        "reason": "generic English request, no proper nouns",
        "confidence": 0.85,
        "latency_ms": 240,
        "cost_usd": 0.0003,
    }
    base.update(overrides)
    return base


class TestGoalClassification:
    def test_happy_path(self) -> None:
        clf = GoalClassification(**_base())
        assert clf.model is PlannerModel.HAIKU
        assert clf.confidence == 0.85
        assert clf.latency_ms == 240
        assert clf.cost_usd == 0.0003

    def test_reason_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GoalClassification(**_base(reason="x" * 201))

    def test_reason_at_max_length_allowed(self) -> None:
        clf = GoalClassification(**_base(reason="x" * 200))
        assert len(clf.reason) == 200

    @pytest.mark.parametrize("bad", [-0.01, 1.01, 1.5, -1.0])
    def test_confidence_out_of_range_rejected(self, bad: float) -> None:
        with pytest.raises(ValidationError):
            GoalClassification(**_base(confidence=bad))

    @pytest.mark.parametrize("ok", [0.0, 0.5, 1.0])
    def test_confidence_bounds_inclusive(self, ok: float) -> None:
        clf = GoalClassification(**_base(confidence=ok))
        assert clf.confidence == ok

    def test_negative_latency_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GoalClassification(**_base(latency_ms=-1))

    def test_negative_cost_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GoalClassification(**_base(cost_usd=-0.0001))

    def test_immutable(self) -> None:
        clf = GoalClassification(**_base())
        with pytest.raises(ValidationError):
            clf.confidence = 0.1  # type: ignore[misc]
