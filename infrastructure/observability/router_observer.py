"""RouterObservingEventBus — taps GoalClassified events for metrics + logs.

Architectural shape: ``PlannerModelRouter`` (domain) only knows about
``EventBusPort``. To attach Prometheus-style metrics and structured logs
without dragging logging / metrics into the domain layer, we wrap the
real bus with this infrastructure-side adapter.

Per ``GoalClassified``:
1. ``RouterMetrics.record(event)`` — increments counter, appends latency.
2. One INFO log line carrying ``goal_hash``, ``chosen_model``,
   ``reason_category``, ``classifier_latency_ms``, ``classifier_cost_usd``.
3. Forwards to the inner bus (errors propagate — the router itself
   already wraps publish in try/except per AD-5, swallowing here would
   mask integration bugs).

Non-``GoalClassified`` events flow through untouched.

Privacy: only ``goal_hash`` (sha256[:16]) ever appears in logs; the raw
goal string is never carried by the event in the first place.
"""

from __future__ import annotations

import logging

from domain.ports.event_bus import EventBusPort
from domain.value_objects.council_events import DebateEvent, GoalClassified
from infrastructure.metrics.router_metrics import RouterMetrics

logger = logging.getLogger(__name__)


class RouterObservingEventBus(EventBusPort):
    """Decorates an ``EventBusPort`` with router metrics + structured logs."""

    def __init__(self, *, inner: EventBusPort, metrics: RouterMetrics) -> None:
        self._inner = inner
        self._metrics = metrics

    async def publish(self, event: DebateEvent) -> None:
        if isinstance(event, GoalClassified):
            self._metrics.record(event)
            logger.info(
                "planner_route_decided "
                "goal_hash=%s chosen_model=%s reason_category=%s "
                "classifier_latency_ms=%d classifier_cost_usd=%s",
                event.goal_hash,
                event.chosen_model.value,
                event.reason_category,
                event.classifier_latency_ms,
                event.classifier_cost_usd,
            )
        await self._inner.publish(event)
