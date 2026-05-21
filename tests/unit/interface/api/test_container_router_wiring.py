"""Tests for PlannerModelRouter DI wiring in AppContainer (T091 RED).

Verifies that ``AppContainer`` constructs and injects a ``PlannerModelRouter``
into ``LLMPlanner`` according to the ``planner_router_mode`` setting and the
classifier-selection policy:

- ``mode="disabled"`` → ``LLMPlanner._router is None`` (byte-identical to pre-router)
- ``mode="enabled"`` + ``local_first`` + no anthropic key → ``LocalGoalClassifier``
- ``mode="enabled"`` + ``anthropic_api_key`` set → ``LLMGoalClassifier``
- Thresholds (confidence / timeout) flow into the constructed router.

This is the AppContainer side of TD-195 (spec.md / plan.md AD-2/AD-3).
"""

from __future__ import annotations

import pytest

from interface.api.container import AppContainer
from tests.unit.interface.test_fractal_container_wiring import _FakeSettings


def _make_router_settings(**overrides: object) -> _FakeSettings:
    s = _FakeSettings()
    s.execution_engine = "fractal"
    # Router defaults — extending the shared _FakeSettings (which predates TD-195).
    s.planner_router_mode = "disabled"  # type: ignore[attr-defined]
    s.planner_router_haiku_confidence_threshold = 0.7  # type: ignore[attr-defined]
    s.planner_router_classifier_timeout_ms = 1500  # type: ignore[attr-defined]
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


# ---------------------------------------------------------------------------
# Disabled mode — no router
# ---------------------------------------------------------------------------


class TestRouterDisabledMode:
    def test_planner_has_no_router_when_mode_disabled(self) -> None:
        container = AppContainer(
            settings=_make_router_settings(planner_router_mode="disabled")
        )
        planner = container.task_engine._planner
        assert planner._router is None


# ---------------------------------------------------------------------------
# Enabled — local classifier branch
# ---------------------------------------------------------------------------


class TestRouterEnabledLocal:
    def test_local_first_no_api_key_uses_local_classifier(self) -> None:
        from domain.services.planner_model_router import PlannerModelRouter
        from infrastructure.routing.local_goal_classifier import LocalGoalClassifier

        container = AppContainer(
            settings=_make_router_settings(
                planner_router_mode="enabled",
                local_first=True,
                anthropic_api_key="",
            )
        )
        planner = container.task_engine._planner
        assert isinstance(planner._router, PlannerModelRouter)
        assert isinstance(planner._router._classifier, LocalGoalClassifier)


# ---------------------------------------------------------------------------
# Enabled — remote classifier branch
# ---------------------------------------------------------------------------


class TestRouterEnabledRemote:
    def test_anthropic_key_uses_remote_classifier(self) -> None:
        from domain.services.planner_model_router import PlannerModelRouter
        from infrastructure.routing.llm_goal_classifier import LLMGoalClassifier

        container = AppContainer(
            settings=_make_router_settings(
                planner_router_mode="enabled",
                local_first=False,
                anthropic_api_key="sk-test-key",
            )
        )
        planner = container.task_engine._planner
        assert isinstance(planner._router, PlannerModelRouter)
        assert isinstance(planner._router._classifier, LLMGoalClassifier)

    def test_anthropic_key_overrides_local_first(self) -> None:
        """When both ``local_first`` and ``anthropic_api_key`` are set, the
        remote classifier wins — explicit credentials trump the local-first
        default per AD-2 ("local is fallback, not policy")."""
        from infrastructure.routing.llm_goal_classifier import LLMGoalClassifier

        container = AppContainer(
            settings=_make_router_settings(
                planner_router_mode="enabled",
                local_first=True,
                anthropic_api_key="sk-test-key",
            )
        )
        planner = container.task_engine._planner
        assert isinstance(planner._router._classifier, LLMGoalClassifier)


# ---------------------------------------------------------------------------
# Threshold + timeout propagation
# ---------------------------------------------------------------------------


class TestThresholdsPropagated:
    def test_confidence_threshold_propagated(self) -> None:
        container = AppContainer(
            settings=_make_router_settings(
                planner_router_mode="enabled",
                local_first=True,
                planner_router_haiku_confidence_threshold=0.85,
            )
        )
        router = container.task_engine._planner._router
        assert router._threshold == pytest.approx(0.85)

    def test_timeout_ms_propagated(self) -> None:
        container = AppContainer(
            settings=_make_router_settings(
                planner_router_mode="enabled",
                local_first=True,
                planner_router_classifier_timeout_ms=2500,
            )
        )
        router = container.task_engine._planner._router
        assert router._timeout_s == pytest.approx(2.5)


# ---------------------------------------------------------------------------
# Non-fractal engine — no router wiring at all
# ---------------------------------------------------------------------------


class TestNonFractalDoesNotWireRouter:
    def test_langgraph_mode_has_no_planner_attribute(self) -> None:
        """In langgraph mode there is no ``LLMPlanner`` to attach a router to;
        the router-construction branch must short-circuit cleanly."""
        container = AppContainer(
            settings=_make_router_settings(
                execution_engine="langgraph",
                planner_router_mode="enabled",
                local_first=True,
            )
        )
        assert not hasattr(container.task_engine, "_planner")
