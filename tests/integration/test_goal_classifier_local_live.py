"""Live integration test for ``LocalGoalClassifier`` (T110).

Exercises the production ``LocalGoalClassifier`` against a real Ollama
qwen3:8b daemon. Skipped automatically when Ollama isn't running so the
unit suite stays portable.

Run::

    uv run --extra dev pytest \
        tests/integration/test_goal_classifier_local_live.py -v -s -m live

Prereqs:
- ``ollama`` CLI installed and serving ``qwen3:8b``

Cost: $0 (local-only).

The three goals exercise the AD-3 reason categories:
- "Build REST API in Python" → expect HAIKU (generic_tech_english)
- 東京から京都への新幹線の最安ルートを調査 → expect SONNET (non_ascii_entity)
- "Generate a Python script that sorts a CSV file by the 'date' column"
  → expect SONNET (quoted_specific_entity)

The privacy invariant (FR-11 / spec.md §Risks) is asserted: the raw goal
string MUST NEVER appear in the published ``GoalClassified`` event payload.
"""

from __future__ import annotations

import shutil

import httpx
import pytest

from domain.services.planner_model_router import PlannerModelRouter
from domain.value_objects.council_events import GoalClassified
from domain.value_objects.planner_model import PlannerModel
from infrastructure.events.in_memory_event_bus import InMemoryEventBus
from infrastructure.llm.cost_tracker import CostTracker
from infrastructure.llm.litellm_gateway import LiteLLMGateway
from infrastructure.llm.ollama_manager import OllamaManager
from infrastructure.metrics.router_metrics import RouterMetrics
from infrastructure.observability.router_observer import RouterObservingEventBus
from infrastructure.persistence.in_memory import InMemoryCostRepository
from infrastructure.routing.local_goal_classifier import LocalGoalClassifier
from shared.config import Settings


def _ollama_running() -> bool:
    if shutil.which("ollama") is None:
        return False
    try:
        r = httpx.get("http://localhost:11434/api/tags", timeout=1.0)
        return r.status_code == 200
    except Exception:
        return False


_HAS_OLLAMA = _ollama_running()

pytestmark = [
    pytest.mark.live,
    pytest.mark.asyncio,
    pytest.mark.skipif(not _HAS_OLLAMA, reason="Ollama daemon not reachable"),
]


def _make_classifier_and_router() -> tuple[
    LocalGoalClassifier, PlannerModelRouter, InMemoryEventBus, RouterMetrics
]:
    settings = Settings(_env_file=None)
    ollama = OllamaManager(base_url=settings.ollama_base_url)
    cost_tracker = CostTracker(cost_repo=InMemoryCostRepository())
    gateway = LiteLLMGateway(ollama=ollama, cost_tracker=cost_tracker, settings=settings)
    classifier = LocalGoalClassifier(gateway=gateway)

    inner_bus = InMemoryEventBus()
    metrics = RouterMetrics()
    bus = RouterObservingEventBus(inner=inner_bus, metrics=metrics)
    router = PlannerModelRouter(
        classifier=classifier,
        event_bus=bus,
        enabled=True,
        haiku_confidence_threshold=0.7,
        classifier_timeout_ms=15_000,  # qwen3:8b is slow on first call
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
async def test_local_classifier_routes_three_goals(
    goal: str, expected_model: PlannerModel
) -> None:
    """Live qwen3:8b classifier picks the expected model per AD-3 buckets."""
    _classifier, router, inner_bus, metrics = _make_classifier_and_router()

    chosen_model, classification = await router.select_for(goal)

    assert chosen_model is expected_model, (
        f"goal={goal!r} expected {expected_model} got {chosen_model} "
        f"(classification={classification})"
    )

    # Exactly one event was published.
    assert len(inner_bus.events) == 1
    event = inner_bus.events[0]
    assert isinstance(event, GoalClassified)
    assert event.chosen_model is expected_model
    assert event.classifier_latency_ms >= 0
    assert event.classifier_cost_usd == 0.0  # local is free

    # Privacy invariant: raw goal MUST NOT appear in the event payload.
    payload = event.model_dump_json()
    assert goal not in payload, "Raw goal leaked into GoalClassified payload"

    # Metrics tap fired.
    assert sum(metrics.decisions_total.values()) == 1
