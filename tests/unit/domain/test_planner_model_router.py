"""Tests for PlannerModelRouter (T040 RED).

Covers all behaviors enumerated in tasks.md:T040 and plan.md AD-2 + AD-3:

1. router-disabled returns (default_model, None) and does NOT call classifier
2. router-enabled + Haiku high-confidence (≥ 0.7) → Haiku, event emitted
3. router-enabled + Haiku low-confidence (< 0.7) → Sonnet, reason prefix,
   category `low_confidence`
4. router-enabled + classifier raises → Sonnet, category `classifier_failed`
5. router-enabled + classifier timeout > classifier_timeout_ms → Sonnet,
   category `classifier_failed`
6. AD-3 reason-category normalization covers all 6 buckets
7. Event-emission failure does NOT abort routing
8. `goal_hash` is sha256(goal)[:16]; raw goal NEVER appears in event payload
"""

from __future__ import annotations

import asyncio
import hashlib
import json

import pytest

from domain.ports.event_bus import EventBusPort
from domain.services.planner_model_router import PlannerModelRouter
from domain.value_objects.council_events import DebateEvent, GoalClassified
from domain.value_objects.goal_classification import GoalClassification
from domain.value_objects.planner_model import PlannerModel
from tests.unit.application._fakes.in_memory_event_bus import FakeEventBus
from tests.unit.application._fakes.in_memory_goal_classifier import (
    InMemoryGoalClassifier,
)


def _verdict(
    model: PlannerModel = PlannerModel.HAIKU,
    confidence: float = 0.9,
    reason: str = "generic technical English goal",
) -> GoalClassification:
    return GoalClassification(
        model=model,
        reason=reason,
        confidence=confidence,
        latency_ms=42,
        cost_usd=0.0004,
    )


def _router(
    classifier: InMemoryGoalClassifier,
    event_bus: EventBusPort,
    *,
    enabled: bool = True,
    threshold: float = 0.7,
    timeout_ms: int = 1500,
) -> PlannerModelRouter:
    return PlannerModelRouter(
        classifier=classifier,
        event_bus=event_bus,
        enabled=enabled,
        haiku_confidence_threshold=threshold,
        classifier_timeout_ms=timeout_ms,
    )


class TestRouterDisabled:
    @pytest.mark.asyncio
    async def test_disabled_returns_default_without_classifier_call(self) -> None:
        clf = InMemoryGoalClassifier(default_response=_verdict())
        bus = FakeEventBus()
        router = _router(clf, bus, enabled=False)

        chosen, classification = await router.select_for("anything")

        assert chosen is PlannerModel.SONNET
        assert classification is None
        assert clf.calls == []
        assert bus.events == []


class TestRouterEnabledHaikuHighConfidence:
    @pytest.mark.asyncio
    async def test_routes_haiku_and_emits_event(self) -> None:
        clf = InMemoryGoalClassifier(
            default_response=_verdict(PlannerModel.HAIKU, 0.9, "generic English")
        )
        bus = FakeEventBus()
        router = _router(clf, bus)

        chosen, classification = await router.select_for("write a python fib")

        assert chosen is PlannerModel.HAIKU
        assert classification is not None
        assert classification.model is PlannerModel.HAIKU
        assert len(bus.events) == 1
        ev = bus.events[0]
        assert isinstance(ev, GoalClassified)
        assert ev.chosen_model is PlannerModel.HAIKU
        assert ev.reason_category == "generic_tech_english"

    @pytest.mark.asyncio
    async def test_threshold_boundary_inclusive(self) -> None:
        clf = InMemoryGoalClassifier(
            default_response=_verdict(PlannerModel.HAIKU, 0.7, "generic")
        )
        bus = FakeEventBus()
        router = _router(clf, bus, threshold=0.7)

        chosen, _ = await router.select_for("goal")
        assert chosen is PlannerModel.HAIKU


class TestRouterEnabledLowConfidence:
    @pytest.mark.asyncio
    async def test_haiku_low_confidence_falls_back_to_sonnet(self) -> None:
        clf = InMemoryGoalClassifier(
            default_response=_verdict(PlannerModel.HAIKU, 0.5, "uncertain")
        )
        bus = FakeEventBus()
        router = _router(clf, bus, threshold=0.7)

        chosen, classification = await router.select_for("ambiguous goal")

        assert chosen is PlannerModel.SONNET
        assert classification is not None
        assert classification.reason.startswith("low_confidence:")
        assert len(bus.events) == 1
        ev = bus.events[0]
        assert isinstance(ev, GoalClassified)
        assert ev.chosen_model is PlannerModel.SONNET
        assert ev.reason_category == "low_confidence"


class TestRouterEnabledClassifierFailed:
    @pytest.mark.asyncio
    async def test_classifier_raises_routes_sonnet(self) -> None:
        clf = InMemoryGoalClassifier(raise_on_call=RuntimeError("LLM down"))
        bus = FakeEventBus()
        router = _router(clf, bus)

        chosen, classification = await router.select_for("goal")

        assert chosen is PlannerModel.SONNET
        assert classification is not None
        assert classification.reason.startswith("classifier_failed:")
        assert "LLM down" in classification.reason
        assert len(bus.events) == 1
        ev = bus.events[0]
        assert isinstance(ev, GoalClassified)
        assert ev.reason_category == "classifier_failed"

    @pytest.mark.asyncio
    async def test_classifier_timeout_routes_sonnet(self) -> None:
        class SlowClassifier(InMemoryGoalClassifier):
            async def classify(self, goal: str) -> GoalClassification:
                await asyncio.sleep(1.0)
                return _verdict(PlannerModel.HAIKU, 0.9)

        clf = SlowClassifier()
        bus = FakeEventBus()
        router = _router(clf, bus, timeout_ms=50)

        chosen, classification = await router.select_for("goal")

        assert chosen is PlannerModel.SONNET
        assert classification is not None
        assert classification.reason.startswith("classifier_failed:")
        assert len(bus.events) == 1
        ev = bus.events[0]
        assert isinstance(ev, GoalClassified)
        assert ev.reason_category == "classifier_failed"


class TestReasonCategoryNormalization:
    @pytest.mark.parametrize(
        "model,confidence,reason_text,expected_category,expected_routed",
        [
            (
                PlannerModel.HAIKU,
                0.9,
                "generic tech English",
                "generic_tech_english",
                PlannerModel.HAIKU,
            ),
            (
                PlannerModel.SONNET,
                0.95,
                "Japanese characters detected in goal",
                "non_ascii_entity",
                PlannerModel.SONNET,
            ),
            (
                PlannerModel.SONNET,
                0.95,
                "non-ASCII / CJK content",
                "non_ascii_entity",
                PlannerModel.SONNET,
            ),
            (
                PlannerModel.SONNET,
                0.95,
                "quoted specific filename present",
                "quoted_specific_entity",
                PlannerModel.SONNET,
            ),
            (
                PlannerModel.SONNET,
                0.95,
                "specific column name referenced",
                "quoted_specific_entity",
                PlannerModel.SONNET,
            ),
            (
                PlannerModel.SONNET,
                0.95,
                "multilingual proper noun referenced",
                "multilingual_or_proper_noun",
                PlannerModel.SONNET,
            ),
            (
                PlannerModel.HAIKU,
                0.4,
                "uncertain classification",
                "low_confidence",
                PlannerModel.SONNET,
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_categories(
        self,
        model: PlannerModel,
        confidence: float,
        reason_text: str,
        expected_category: str,
        expected_routed: PlannerModel,
    ) -> None:
        clf = InMemoryGoalClassifier(
            default_response=_verdict(model, confidence, reason_text)
        )
        bus = FakeEventBus()
        router = _router(clf, bus)

        chosen, _ = await router.select_for("input goal")

        assert chosen is expected_routed
        assert len(bus.events) == 1
        ev = bus.events[0]
        assert isinstance(ev, GoalClassified)
        assert ev.reason_category == expected_category


class TestEventEmissionResilience:
    @pytest.mark.asyncio
    async def test_event_publish_failure_does_not_abort_routing(self) -> None:
        class FailingBus(EventBusPort):
            async def publish(self, event: DebateEvent) -> None:
                raise RuntimeError("event bus down")

        clf = InMemoryGoalClassifier(default_response=_verdict(PlannerModel.HAIKU, 0.9))
        router = _router(clf, FailingBus())

        chosen, classification = await router.select_for("goal")

        assert chosen is PlannerModel.HAIKU
        assert classification is not None


class TestPrivacyGoalHash:
    @pytest.mark.asyncio
    async def test_goal_hash_is_sha256_truncated_16(self) -> None:
        goal = "secret proprietary goal text"
        expected = hashlib.sha256(goal.encode("utf-8")).hexdigest()[:16]

        clf = InMemoryGoalClassifier(default_response=_verdict(PlannerModel.HAIKU, 0.9))
        bus = FakeEventBus()
        router = _router(clf, bus)

        await router.select_for(goal)

        assert len(bus.events) == 1
        ev = bus.events[0]
        assert isinstance(ev, GoalClassified)
        assert ev.goal_hash == expected

    @pytest.mark.asyncio
    async def test_raw_goal_never_in_event_payload(self) -> None:
        goal = "SuperSecretProjectXyz123"
        clf = InMemoryGoalClassifier(default_response=_verdict(PlannerModel.HAIKU, 0.9))
        bus = FakeEventBus()
        router = _router(clf, bus)

        await router.select_for(goal)

        ev = bus.events[0]
        payload = ev.model_dump_json()
        assert goal not in payload
        as_dict = json.loads(payload)
        assert "goal" not in as_dict
        assert "raw_goal" not in as_dict
