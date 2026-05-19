"""Live integration test for ``LLMGoalClassifier`` (T111).

Exercises the production ``LLMGoalClassifier`` (Anthropic Haiku 4.5) end
to end through ``LiteLLMGateway`` + ``PlannerModelRouter``.

Run: ``uv run --extra dev pytest tests/integration/test_goal_classifier_remote_live.py -v -s -m live``

Prereqs:
- ``ANTHROPIC_API_KEY`` env var set (or ``shared/config`` carries it).

Cost: ≤ $0.003 total (3 short Haiku calls, ~250 tokens each).

Same 3-goal matrix as the local test (T110) so the two classifiers can be
A/B compared offline.
"""

from __future__ import annotations

import os

import pytest

from domain.services.planner_model_router import PlannerModelRouter
from domain.value_objects.council_events import GoalClassified
from domain.value_objects.planner_model import PlannerModel
from infrastructure.events.in_memory_event_bus import InMemoryEventBus
from infrastructure.llm.cost_tracker import CostTracker
from infrastructure.llm.litellm_gateway import LiteLLMGateway
from infrastructure.llm.ollama_manager import OllamaManager
from infrastructure.persistence.in_memory import InMemoryCostRepository
from infrastructure.metrics.router_metrics import RouterMetrics
from infrastructure.observability.router_observer import RouterObservingEventBus
from infrastructure.routing.llm_goal_classifier import LLMGoalClassifier
from shared.config import Settings


def _has_anthropic_key() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    try:
        return bool(Settings().anthropic_api_key)
    except Exception:
        return False


_HAS_ANTHROPIC = _has_anthropic_key()

pytestmark = [
    pytest.mark.live,
    pytest.mark.asyncio,
    pytest.mark.skipif(not _HAS_ANTHROPIC, reason="ANTHROPIC_API_KEY not set"),
]


def _make_classifier_and_router() -> tuple[
    LLMGoalClassifier, PlannerModelRouter, InMemoryEventBus, RouterMetrics
]:
    settings = Settings(_env_file=None)
    ollama = OllamaManager(base_url=settings.ollama_base_url)
    cost_tracker = CostTracker(cost_repo=InMemoryCostRepository())
    gateway = LiteLLMGateway(ollama=ollama, cost_tracker=cost_tracker, settings=settings)
    classifier = LLMGoalClassifier(gateway=gateway)

    inner_bus = InMemoryEventBus()
    metrics = RouterMetrics()
    bus = RouterObservingEventBus(inner=inner_bus, metrics=metrics)
    router = PlannerModelRouter(
        classifier=classifier,
        event_bus=bus,
        enabled=True,
        haiku_confidence_threshold=0.7,
        classifier_timeout_ms=5_000,
    )
    return classifier, router, inner_bus, metrics


@pytest.mark.parametrize(
    ("goal", "expected_model"),
    [
        ("Build REST API in Python", PlannerModel.HAIKU),
        ("東京から京都への新幹線の最安ルートを調査", PlannerModel.SONNET),
        (
            "Generate a Python script that sorts a CSV file by the 'date' column",
            PlannerModel.SONNET,
        ),
    ],
)
async def test_remote_classifier_routes_three_goals(
    goal: str, expected_model: PlannerModel
) -> None:
    """Live Haiku 4.5 classifier picks the expected model per AD-3 buckets."""
    _classifier, router, inner_bus, metrics = _make_classifier_and_router()

    chosen_model, classification = await router.select_for(goal)

    assert chosen_model is expected_model, (
        f"goal={goal!r} expected {expected_model} got {chosen_model} "
        f"(classification={classification})"
    )

    assert len(inner_bus.events) == 1
    event = inner_bus.events[0]
    assert isinstance(event, GoalClassified)
    assert event.chosen_model is expected_model
    assert event.classifier_latency_ms >= 0
    # Haiku 4.5 pricing: ≤ $0.001 per short call (observed ~$0.0007).
    assert 0.0 <= event.classifier_cost_usd <= 0.001

    # Privacy invariant: raw goal MUST NOT appear in the event payload.
    payload = event.model_dump_json()
    assert goal not in payload, "Raw goal leaked into GoalClassified payload"

    # Metrics tap fired.
    assert sum(metrics.decisions_total.values()) == 1
