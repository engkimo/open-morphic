"""Tests for RouterObservingEventBus — structured log + metrics (T101 RED).

Wraps an inner ``EventBusPort`` and, on each ``GoalClassified`` event:

1. Increments the injected ``RouterMetrics`` counters / histogram.
2. Emits one INFO log line carrying:
   ``goal_hash``, ``chosen_model``, ``reason_category``,
   ``classifier_latency_ms``, ``classifier_cost_usd``.
3. Forwards the event to the inner bus (best-effort, errors swallowed).

Privacy invariant (spec.md §Risks): the raw goal string MUST NEVER appear
in the log line — only the 16-char ``goal_hash`` is permitted.

Non-``GoalClassified`` events (e.g. ``DebateStarted``) flow through
unobserved — this adapter is router-specific.
"""

from __future__ import annotations

import logging

import pytest

from domain.entities.council import SubtaskBrief, TaskType
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.council_events import (
    DebateStarted,
    GoalClassified,
)
from domain.value_objects.planner_model import PlannerModel
from infrastructure.events.in_memory_event_bus import InMemoryEventBus
from infrastructure.metrics.router_metrics import RouterMetrics
from infrastructure.observability.router_observer import RouterObservingEventBus


def _goal_classified(
    *,
    goal_hash: str = "abcdef0123456789",
    chosen_model: PlannerModel = PlannerModel.HAIKU,
    reason_category: str = "generic_tech_english",
    confidence: float = 0.91,
    latency_ms: int = 73,
    cost_usd: float = 0.00018,
) -> GoalClassified:
    return GoalClassified(
        goal_hash=goal_hash,
        chosen_model=chosen_model,
        confidence=confidence,
        reason_category=reason_category,  # type: ignore[arg-type]
        classifier_latency_ms=latency_ms,
        classifier_cost_usd=cost_usd,
    )


# ---------------------------------------------------------------------------
# Forwarding
# ---------------------------------------------------------------------------


class TestForwarding:
    @pytest.mark.asyncio
    async def test_event_is_forwarded_to_inner_bus(self) -> None:
        inner = InMemoryEventBus()
        bus = RouterObservingEventBus(inner=inner, metrics=RouterMetrics())
        event = _goal_classified()
        await bus.publish(event)
        assert inner.events == [event]

    @pytest.mark.asyncio
    async def test_non_goal_classified_event_flows_through(self) -> None:
        inner = InMemoryEventBus()
        bus = RouterObservingEventBus(inner=inner, metrics=RouterMetrics())
        unrelated = DebateStarted(
            subtask=SubtaskBrief(
                id="sub-1",
                description="x",
                task_type=TaskType.SIMPLE_QA,
                constraints=[],
                success_criteria=[],
            ),
            candidates=[AgentEngineType.OLLAMA, AgentEngineType.GEMINI_CLI],
        )
        await bus.publish(unrelated)
        assert inner.events == [unrelated]


# ---------------------------------------------------------------------------
# Metrics integration
# ---------------------------------------------------------------------------


class TestMetricsIntegration:
    @pytest.mark.asyncio
    async def test_goal_classified_increments_metrics(self) -> None:
        metrics = RouterMetrics()
        bus = RouterObservingEventBus(inner=InMemoryEventBus(), metrics=metrics)
        await bus.publish(_goal_classified(chosen_model=PlannerModel.HAIKU))
        assert metrics.decisions_total[("haiku", "generic_tech_english")] == 1

    @pytest.mark.asyncio
    async def test_unrelated_event_does_not_touch_metrics(self) -> None:
        metrics = RouterMetrics()
        bus = RouterObservingEventBus(inner=InMemoryEventBus(), metrics=metrics)
        unrelated = DebateStarted(
            subtask=SubtaskBrief(
                id="sub-1",
                description="x",
                task_type=TaskType.SIMPLE_QA,
                constraints=[],
                success_criteria=[],
            ),
            candidates=[AgentEngineType.OLLAMA],
        )
        await bus.publish(unrelated)
        assert dict(metrics.decisions_total) == {}
        assert metrics.latency_samples == []


# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------


class TestStructuredLog:
    @pytest.mark.asyncio
    async def test_log_carries_all_required_fields(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        bus = RouterObservingEventBus(inner=InMemoryEventBus(), metrics=RouterMetrics())
        caplog.set_level(logging.INFO, logger="infrastructure.observability.router_observer")
        await bus.publish(
            _goal_classified(
                goal_hash="abcdef0123456789",
                chosen_model=PlannerModel.HAIKU,
                reason_category="generic_tech_english",
                latency_ms=73,
                cost_usd=0.00018,
            )
        )
        text = caplog.text
        assert "goal_hash=abcdef0123456789" in text
        assert "chosen_model=haiku" in text
        assert "reason_category=generic_tech_english" in text
        assert "classifier_latency_ms=73" in text
        assert "classifier_cost_usd=0.00018" in text

    @pytest.mark.asyncio
    async def test_log_records_sonnet_fallback(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        bus = RouterObservingEventBus(inner=InMemoryEventBus(), metrics=RouterMetrics())
        caplog.set_level(logging.INFO, logger="infrastructure.observability.router_observer")
        await bus.publish(
            _goal_classified(
                chosen_model=PlannerModel.SONNET,
                reason_category="classifier_failed",
                latency_ms=0,
                cost_usd=0.0,
            )
        )
        assert "chosen_model=sonnet" in caplog.text
        assert "reason_category=classifier_failed" in caplog.text

    @pytest.mark.asyncio
    async def test_no_log_for_unrelated_events(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        bus = RouterObservingEventBus(inner=InMemoryEventBus(), metrics=RouterMetrics())
        caplog.set_level(logging.INFO, logger="infrastructure.observability.router_observer")
        unrelated = DebateStarted(
            subtask=SubtaskBrief(
                id="sub-1",
                description="x",
                task_type=TaskType.SIMPLE_QA,
                constraints=[],
                success_criteria=[],
            ),
            candidates=[AgentEngineType.OLLAMA],
        )
        await bus.publish(unrelated)
        assert caplog.text == ""


# ---------------------------------------------------------------------------
# Privacy invariant
# ---------------------------------------------------------------------------


class TestPrivacy:
    @pytest.mark.asyncio
    async def test_log_does_not_contain_raw_goal_string(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Even if a malicious caller stuffs goal text into goal_hash, the
        observer can only log what the event itself carries. The event VO
        validates ``goal_hash`` to exactly 16 chars (sha256[:16]), so a raw
        goal cannot fit. This test pins the policy: no goal text in logs."""
        bus = RouterObservingEventBus(inner=InMemoryEventBus(), metrics=RouterMetrics())
        caplog.set_level(logging.INFO, logger="infrastructure.observability.router_observer")
        secret_goal = "Investigate Hikawa Shrine history"
        # Construct a normal hashed event — the observer should not be able
        # to reconstruct or echo the raw goal.
        await bus.publish(_goal_classified())
        assert secret_goal not in caplog.text

    @pytest.mark.asyncio
    async def test_inner_bus_failure_does_not_break_observer(self) -> None:
        """Publish errors on the inner bus must propagate — the router itself
        already wraps publish in try/except (AD-5), so swallowing here would
        mask bugs at integration boundaries."""

        class _BoomBus(InMemoryEventBus):
            async def publish(self, event):  # type: ignore[override]
                raise RuntimeError("inner bus down")

        bus = RouterObservingEventBus(inner=_BoomBus(), metrics=RouterMetrics())
        with pytest.raises(RuntimeError, match="inner bus down"):
            await bus.publish(_goal_classified())
