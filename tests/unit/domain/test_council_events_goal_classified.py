"""Tests for GoalClassified event variant (T012 RED).

Additive extension of the DebateEvent discriminated union — existing
variants (DebateStarted, ArgumentSubmitted, DecisionResolved,
DebateAbandoned) must remain byte-identical.
"""

from __future__ import annotations

import json

from domain.value_objects.council_events import (
    DebateEvent,
    DebateEventAdapter,
    GoalClassified,
)
from domain.value_objects.planner_model import PlannerModel


def _hash16() -> str:
    return "a" * 16


class TestGoalClassifiedVariant:
    def test_constructable(self) -> None:
        ev = GoalClassified(
            goal_hash=_hash16(),
            chosen_model=PlannerModel.HAIKU,
            confidence=0.91,
            reason_category="generic_tech_english",
            classifier_latency_ms=210,
            classifier_cost_usd=0.0003,
        )
        assert ev.kind == "goal_classified"
        assert ev.chosen_model is PlannerModel.HAIKU
        assert ev.reason_category == "generic_tech_english"

    def test_kind_discriminator_is_fixed(self) -> None:
        ev = GoalClassified(
            goal_hash=_hash16(),
            chosen_model=PlannerModel.SONNET,
            confidence=0.5,
            reason_category="low_confidence",
            classifier_latency_ms=180,
            classifier_cost_usd=0.0002,
        )
        # Pydantic Literal — assigning a different value raises.
        dumped = ev.model_dump()
        assert dumped["kind"] == "goal_classified"

    def test_json_round_trip_via_union_adapter(self) -> None:
        original = GoalClassified(
            goal_hash=_hash16(),
            chosen_model=PlannerModel.SONNET,
            confidence=0.42,
            reason_category="classifier_failed",
            classifier_latency_ms=1500,
            classifier_cost_usd=0.0,
        )
        raw = original.model_dump_json()
        parsed: DebateEvent = DebateEventAdapter.validate_json(raw)
        assert isinstance(parsed, GoalClassified)
        assert parsed.chosen_model is PlannerModel.SONNET
        assert parsed.reason_category == "classifier_failed"

    def test_existing_variants_still_resolve(self) -> None:
        # Sanity: union still discriminates by `kind`.
        from domain.entities.cognitive import Decision
        from domain.value_objects.council_events import DebateAbandoned

        abandoned = DebateAbandoned(reason="quorum lost")
        raw = abandoned.model_dump_json()
        parsed = DebateEventAdapter.validate_json(raw)
        assert parsed.kind == "debate_abandoned"
        _ = Decision  # imported to confirm domain module untouched

    def test_raw_goal_field_does_not_exist(self) -> None:
        ev = GoalClassified(
            goal_hash=_hash16(),
            chosen_model=PlannerModel.HAIKU,
            confidence=0.8,
            reason_category="generic_tech_english",
            classifier_latency_ms=200,
            classifier_cost_usd=0.0003,
        )
        payload = json.loads(ev.model_dump_json())
        assert "goal" not in payload
        assert "raw_goal" not in payload
