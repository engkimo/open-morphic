"""Tests for RouterMetrics — Prometheus-style counters + histogram (T100 RED).

The router metrics adapter is **dependency-free** (no `prometheus_client`
yet — the project doesn't ship it). It exposes a small API shaped like
what a future Prometheus exporter would consume:

- ``record(event: GoalClassified)`` — increments a counter keyed by
  ``(chosen_model_label, reason_category)`` and appends ``classifier_latency_ms``
  to a histogram bucket.
- ``decisions_total`` — dict ``{(model_label, reason_category): count}``
  (read-only view).
- ``latency_samples`` — list[int] of recorded latency_ms values.

FR-12: counter is ``morphic_goal_classifier_decisions_total{model, reason_category}``;
histogram is ``morphic_goal_classifier_latency_ms``.

Cardinality bound: only the 6 closed ``ReasonCategory`` buckets (AD-3) may
appear as labels. Anything else is a type-system / contract bug upstream.
"""

from __future__ import annotations

from domain.value_objects.council_events import GoalClassified, ReasonCategory
from domain.value_objects.planner_model import PlannerModel
from infrastructure.metrics.router_metrics import (
    REASON_CATEGORY_LABELS,
    RouterMetrics,
)


def _event(
    *,
    chosen_model: PlannerModel = PlannerModel.HAIKU,
    reason_category: ReasonCategory = "generic_tech_english",
    confidence: float = 0.9,
    latency_ms: int = 42,
    cost_usd: float = 0.0,
) -> GoalClassified:
    return GoalClassified(
        goal_hash="0" * 16,
        chosen_model=chosen_model,
        confidence=confidence,
        reason_category=reason_category,
        classifier_latency_ms=latency_ms,
        classifier_cost_usd=cost_usd,
    )


# ---------------------------------------------------------------------------
# Counter behavior
# ---------------------------------------------------------------------------


class TestDecisionsCounter:
    def test_single_decision_increments_bucket_by_one(self) -> None:
        m = RouterMetrics()
        m.record(_event())
        assert m.decisions_total[("haiku", "generic_tech_english")] == 1

    def test_multiple_decisions_accumulate(self) -> None:
        m = RouterMetrics()
        for _ in range(5):
            m.record(_event())
        assert m.decisions_total[("haiku", "generic_tech_english")] == 5

    def test_sonnet_and_haiku_tracked_separately(self) -> None:
        m = RouterMetrics()
        m.record(_event(chosen_model=PlannerModel.HAIKU))
        m.record(_event(chosen_model=PlannerModel.SONNET, reason_category="non_ascii_entity"))
        m.record(_event(chosen_model=PlannerModel.SONNET, reason_category="non_ascii_entity"))
        assert m.decisions_total[("haiku", "generic_tech_english")] == 1
        assert m.decisions_total[("sonnet", "non_ascii_entity")] == 2

    def test_initial_counter_is_empty(self) -> None:
        m = RouterMetrics()
        assert dict(m.decisions_total) == {}


# ---------------------------------------------------------------------------
# Histogram behavior
# ---------------------------------------------------------------------------


class TestLatencyHistogram:
    def test_record_appends_latency_sample(self) -> None:
        m = RouterMetrics()
        m.record(_event(latency_ms=42))
        m.record(_event(latency_ms=100))
        assert list(m.latency_samples) == [42, 100]

    def test_initial_histogram_is_empty(self) -> None:
        m = RouterMetrics()
        assert list(m.latency_samples) == []


# ---------------------------------------------------------------------------
# Cardinality bound (AD-3)
# ---------------------------------------------------------------------------


class TestLabelCardinality:
    def test_reason_category_labels_match_ad3_buckets(self) -> None:
        """REASON_CATEGORY_LABELS is the *closed* set of allowed label values."""
        assert set(REASON_CATEGORY_LABELS) == {
            "generic_tech_english",
            "non_ascii_entity",
            "quoted_specific_entity",
            "multilingual_or_proper_noun",
            "low_confidence",
            "classifier_failed",
        }

    def test_label_cardinality_is_exactly_six(self) -> None:
        assert len(REASON_CATEGORY_LABELS) == 6

    def test_label_cardinality_bounded_after_full_replay(self) -> None:
        """Recording one event per allowed bucket caps active series at 12 (2 × 6)."""
        m = RouterMetrics()
        for cat in REASON_CATEGORY_LABELS:
            for model in (PlannerModel.HAIKU, PlannerModel.SONNET):
                m.record(_event(chosen_model=model, reason_category=cat))
        # 2 models × 6 categories = at most 12 distinct series
        assert len(m.decisions_total) <= 12


# ---------------------------------------------------------------------------
# Snapshot / reset
# ---------------------------------------------------------------------------


class TestSnapshot:
    def test_snapshot_is_a_copy_not_a_view(self) -> None:
        m = RouterMetrics()
        m.record(_event())
        snap = m.snapshot()
        m.record(_event())
        assert snap.decisions_total[("haiku", "generic_tech_english")] == 1
        assert m.decisions_total[("haiku", "generic_tech_english")] == 2

    def test_snapshot_preserves_latency_samples(self) -> None:
        m = RouterMetrics()
        m.record(_event(latency_ms=10))
        m.record(_event(latency_ms=20))
        snap = m.snapshot()
        assert snap.latency_samples == [10, 20]
