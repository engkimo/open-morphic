"""Sanity tests for `InMemoryGoalClassifier` fake (T030)."""

from __future__ import annotations

import pytest

from domain.ports.goal_classifier import GoalClassifierPort
from domain.value_objects.goal_classification import GoalClassification
from domain.value_objects.planner_model import PlannerModel
from tests.unit.application._fakes.in_memory_goal_classifier import (
    InMemoryGoalClassifier,
)


def _verdict(model: PlannerModel = PlannerModel.HAIKU) -> GoalClassification:
    return GoalClassification(
        model=model,
        reason="fake",
        confidence=0.9,
        latency_ms=5,
        cost_usd=0.0,
    )


class TestInMemoryGoalClassifier:
    def test_conforms_to_port(self) -> None:
        assert isinstance(InMemoryGoalClassifier(), GoalClassifierPort)

    @pytest.mark.asyncio
    async def test_consumes_response_queue_in_order(self) -> None:
        first = _verdict(PlannerModel.HAIKU)
        second = _verdict(PlannerModel.SONNET)
        clf = InMemoryGoalClassifier(responses=[first, second])

        assert await clf.classify("g1") is first
        assert await clf.classify("g2") is second

    @pytest.mark.asyncio
    async def test_falls_back_to_default_when_queue_empty(self) -> None:
        default = _verdict(PlannerModel.SONNET)
        clf = InMemoryGoalClassifier(default_response=default)

        assert await clf.classify("anything") is default
        assert await clf.classify("again") is default

    @pytest.mark.asyncio
    async def test_raises_when_exhausted_with_no_default(self) -> None:
        clf = InMemoryGoalClassifier()
        with pytest.raises(IndexError):
            await clf.classify("goal")

    @pytest.mark.asyncio
    async def test_raise_on_call_propagates(self) -> None:
        boom = RuntimeError("upstream LLM down")
        clf = InMemoryGoalClassifier(raise_on_call=boom)

        with pytest.raises(RuntimeError, match="upstream LLM down"):
            await clf.classify("goal")

    @pytest.mark.asyncio
    async def test_calls_recorded_for_assertions(self) -> None:
        clf = InMemoryGoalClassifier(default_response=_verdict())

        await clf.classify("first goal")
        await clf.classify("second goal")

        assert clf.calls == ["first goal", "second goal"]

    @pytest.mark.asyncio
    async def test_empty_goal_rejected_before_queue_consumed(self) -> None:
        clf = InMemoryGoalClassifier(responses=[_verdict()])

        with pytest.raises(ValueError):
            await clf.classify("")

        # Response queue intact for the next valid call.
        verdict = await clf.classify("valid")
        assert verdict.model is PlannerModel.HAIKU

    @pytest.mark.asyncio
    async def test_whitespace_goal_rejected(self) -> None:
        clf = InMemoryGoalClassifier(responses=[_verdict()])
        with pytest.raises(ValueError):
            await clf.classify("   \n\t  ")
