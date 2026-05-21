"""Tests for GoalClassifierPort ABC (T020 RED)."""

from __future__ import annotations

import inspect

import pytest

from domain.ports.goal_classifier import GoalClassifierPort
from domain.value_objects.goal_classification import GoalClassification
from domain.value_objects.planner_model import PlannerModel


class _StubClassifier(GoalClassifierPort):
    async def classify(self, goal: str) -> GoalClassification:
        if not goal or not goal.strip():
            raise ValueError("goal must be non-empty")
        return GoalClassification(
            model=PlannerModel.HAIKU,
            reason="stub",
            confidence=0.9,
            latency_ms=10,
            cost_usd=0.0,
        )


class TestGoalClassifierPort:
    def test_is_abstract(self) -> None:
        assert inspect.isabstract(GoalClassifierPort)

    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            GoalClassifierPort()  # type: ignore[abstract]

    def test_classify_is_abstract_coroutine(self) -> None:
        assert "classify" in GoalClassifierPort.__abstractmethods__
        assert inspect.iscoroutinefunction(_StubClassifier.classify)

    @pytest.mark.asyncio
    async def test_stub_implementation_works(self) -> None:
        clf = _StubClassifier()
        result = await clf.classify("anything")
        assert isinstance(result, GoalClassification)
        assert result.model is PlannerModel.HAIKU

    @pytest.mark.asyncio
    async def test_empty_goal_rejected(self) -> None:
        clf = _StubClassifier()
        with pytest.raises(ValueError):
            await clf.classify("")

    @pytest.mark.asyncio
    async def test_whitespace_goal_rejected(self) -> None:
        clf = _StubClassifier()
        with pytest.raises(ValueError):
            await clf.classify("   \n\t  ")
