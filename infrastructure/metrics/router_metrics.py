"""RouterMetrics — Prometheus-style counters + histogram for the planner router.

Dependency-free MVP (no ``prometheus_client``). The API is shaped like what
a future Prometheus exporter would consume so swap-in is mechanical:

- ``decisions_total`` matches counter ``morphic_goal_classifier_decisions_total``
  with labels ``{model, reason_category}`` (FR-12).
- ``latency_samples`` is the raw observation buffer that a future
  ``Histogram.observe()`` call would receive (FR-12).

Cardinality is bounded by the 2 ``PlannerModel`` values × 6 ``ReasonCategory``
buckets (AD-3) — at most 12 distinct series, regardless of input volume.

The recorder is sync: ``RouterObservingEventBus`` calls it from inside
``publish`` which is already best-effort + exception-swallowed upstream.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import get_args

from domain.value_objects.council_events import GoalClassified, ReasonCategory

REASON_CATEGORY_LABELS: tuple[ReasonCategory, ...] = get_args(ReasonCategory)


@dataclass(frozen=True)
class RouterMetricsSnapshot:
    decisions_total: Mapping[tuple[str, str], int]
    latency_samples: list[int]


@dataclass
class RouterMetrics:
    """In-memory Prometheus-style metrics for planner routing decisions."""

    _decisions: defaultdict[tuple[str, str], int] = field(
        default_factory=lambda: defaultdict(int)
    )
    _latency: list[int] = field(default_factory=list)

    @property
    def decisions_total(self) -> Mapping[tuple[str, str], int]:
        return self._decisions

    @property
    def latency_samples(self) -> list[int]:
        return self._latency

    def record(self, event: GoalClassified) -> None:
        model_label = event.chosen_model.value
        key = (model_label, event.reason_category)
        self._decisions[key] += 1
        self._latency.append(event.classifier_latency_ms)

    def snapshot(self) -> RouterMetricsSnapshot:
        return RouterMetricsSnapshot(
            decisions_total=dict(self._decisions),
            latency_samples=list(self._latency),
        )
