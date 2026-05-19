"""Tests for LLMPlanner ↔ PlannerModelRouter integration (T080 RED).

The planner accepts an optional ``PlannerModelRouter``. When present, it
consults the router with the goal and uses the resolved model id for the
``LLMGateway.complete`` call. The byte-identical system prefix (TD-190)
MUST stay unchanged regardless of routed model.

When the router is ``None`` (the default), behavior is identical to the
pre-router planner (covered by ``test_llm_planner.py``).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from domain.ports.event_bus import EventBusPort
from domain.ports.goal_classifier import GoalClassifierPort
from domain.ports.llm_gateway import LLMGateway, LLMResponse
from domain.services.planner_model_router import PlannerModelRouter
from domain.value_objects.council_events import DebateEvent
from domain.value_objects.goal_classification import GoalClassification
from domain.value_objects.planner_model import PlannerModel
from infrastructure.fractal.llm_planner import _SYSTEM_PROMPT, LLMPlanner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _llm_response(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="test-model",
        prompt_tokens=50,
        completion_tokens=30,
        cost_usd=0.0,
    )


def _extract_messages(llm_mock: AsyncMock) -> list[dict]:
    """Return the messages arg passed to ``llm.complete`` (positional or kw)."""
    call = llm_mock.complete.await_args
    if call.args:
        return call.args[0]
    return call.kwargs["messages"]


def _sample_payload() -> str:
    return json.dumps(
        [
            {
                "description": "Step 1: do something",
                "is_terminal": True,
                "score": 0.9,
                "condition": None,
                "input_artifacts": {},
                "output_artifacts": {},
            }
        ]
    )


class _FixedClassifier(GoalClassifierPort):
    """Returns a single pre-built verdict for any goal."""

    def __init__(self, verdict: GoalClassification) -> None:
        self._verdict = verdict

    async def classify(self, goal: str) -> GoalClassification:
        if not goal or not goal.strip():
            raise ValueError("goal must be non-empty")
        return self._verdict


class _NullEventBus(EventBusPort):
    async def publish(self, event: DebateEvent) -> None:  # type: ignore[override]
        return None


def _haiku_router(*, confidence: float = 0.9) -> PlannerModelRouter:
    return PlannerModelRouter(
        classifier=_FixedClassifier(
            GoalClassification(
                model=PlannerModel.HAIKU,
                reason="generic English",
                confidence=confidence,
                latency_ms=42,
                cost_usd=0.0001,
            )
        ),
        event_bus=_NullEventBus(),
        enabled=True,
    )


def _sonnet_router() -> PlannerModelRouter:
    return PlannerModelRouter(
        classifier=_FixedClassifier(
            GoalClassification(
                model=PlannerModel.SONNET,
                reason="japanese non-ascii",
                confidence=0.92,
                latency_ms=51,
                cost_usd=0.0002,
            )
        ),
        event_bus=_NullEventBus(),
        enabled=True,
    )


def _disabled_router() -> PlannerModelRouter:
    return PlannerModelRouter(
        classifier=_FixedClassifier(
            GoalClassification(
                model=PlannerModel.HAIKU,
                reason="unused",
                confidence=1.0,
                latency_ms=0,
                cost_usd=0.0,
            )
        ),
        event_bus=_NullEventBus(),
        enabled=False,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRouterOverridesModelId:
    @pytest.mark.asyncio
    async def test_haiku_verdict_routes_to_haiku_gateway_id(self) -> None:
        llm = AsyncMock(spec=LLMGateway)
        llm.complete.return_value = _llm_response(_sample_payload())
        planner = LLMPlanner(llm, router=_haiku_router())

        await planner.generate_candidates("Build a Python REST API", "", 0)

        assert llm.complete.await_count == 1
        kwargs = llm.complete.await_args.kwargs
        assert kwargs["model"] == PlannerModel.HAIKU.to_gateway_id()

    @pytest.mark.asyncio
    async def test_sonnet_verdict_routes_to_sonnet_gateway_id(self) -> None:
        llm = AsyncMock(spec=LLMGateway)
        llm.complete.return_value = _llm_response(_sample_payload())
        planner = LLMPlanner(llm, router=_sonnet_router())

        await planner.generate_candidates("氷川神社の歴史を調査", "", 0)

        kwargs = llm.complete.await_args.kwargs
        assert kwargs["model"] == PlannerModel.SONNET.to_gateway_id()

    @pytest.mark.asyncio
    async def test_low_confidence_haiku_demotes_to_sonnet(self) -> None:
        """AD-2: confidence < threshold → Sonnet fallback."""
        llm = AsyncMock(spec=LLMGateway)
        llm.complete.return_value = _llm_response(_sample_payload())
        planner = LLMPlanner(llm, router=_haiku_router(confidence=0.4))

        await planner.generate_candidates("ambiguous task", "", 0)

        kwargs = llm.complete.await_args.kwargs
        assert kwargs["model"] == PlannerModel.SONNET.to_gateway_id()


class TestRouterDisabled:
    @pytest.mark.asyncio
    async def test_disabled_router_uses_default_sonnet(self) -> None:
        llm = AsyncMock(spec=LLMGateway)
        llm.complete.return_value = _llm_response(_sample_payload())
        planner = LLMPlanner(llm, router=_disabled_router())

        await planner.generate_candidates("anything", "", 0)

        kwargs = llm.complete.await_args.kwargs
        assert kwargs["model"] == PlannerModel.SONNET.to_gateway_id()


class TestRouterAbsent:
    """``router=None`` preserves pre-router behavior — explicit ``model`` honored."""

    @pytest.mark.asyncio
    async def test_no_router_passes_constructor_model(self) -> None:
        llm = AsyncMock(spec=LLMGateway)
        llm.complete.return_value = _llm_response(_sample_payload())
        planner = LLMPlanner(llm, model="claude-sonnet-4-6", router=None)

        await planner.generate_candidates("anything", "", 0)

        kwargs = llm.complete.await_args.kwargs
        assert kwargs["model"] == "claude-sonnet-4-6"

    @pytest.mark.asyncio
    async def test_no_router_and_no_model_passes_none(self) -> None:
        llm = AsyncMock(spec=LLMGateway)
        llm.complete.return_value = _llm_response(_sample_payload())
        planner = LLMPlanner(llm)

        await planner.generate_candidates("anything", "", 0)

        kwargs = llm.complete.await_args.kwargs
        assert kwargs["model"] is None


class TestStableSystemPrefix:
    """TD-190: SYSTEM_PROMPT must be byte-identical regardless of routed model."""

    @pytest.mark.asyncio
    async def test_system_message_unchanged_for_haiku_route(self) -> None:
        llm = AsyncMock(spec=LLMGateway)
        llm.complete.return_value = _llm_response(_sample_payload())
        planner = LLMPlanner(llm, router=_haiku_router())

        await planner.generate_candidates("Build a Python REST API", "", 0)

        messages = _extract_messages(llm)
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == _SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_system_message_byte_identical_across_routes(self) -> None:
        llm_a = AsyncMock(spec=LLMGateway)
        llm_a.complete.return_value = _llm_response(_sample_payload())
        planner_a = LLMPlanner(llm_a, router=_haiku_router())
        await planner_a.generate_candidates("English goal", "", 0)

        llm_b = AsyncMock(spec=LLMGateway)
        llm_b.complete.return_value = _llm_response(_sample_payload())
        planner_b = LLMPlanner(llm_b, router=_sonnet_router())
        await planner_b.generate_candidates("日本語のゴール", "", 0)

        sys_a = _extract_messages(llm_a)[0]["content"]
        sys_b = _extract_messages(llm_b)[0]["content"]
        assert sys_a == sys_b == _SYSTEM_PROMPT
