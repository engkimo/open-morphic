"""Tests for planner router settings (T090 RED).

Three new fields on ``Settings``:

- ``planner_router_mode``: "disabled" | "enabled" (env: MORPHIC_PLANNER_ROUTER)
- ``planner_router_haiku_confidence_threshold``: float (default 0.7)
- ``planner_router_classifier_timeout_ms``: int (default 1500)

The default mode is "disabled" so existing deployments are byte-identical to
pre-router behavior until an operator opts in via env.
"""

from __future__ import annotations

import pytest

from shared.config import Settings


class TestPlannerRouterDefaults:
    def test_mode_defaults_to_disabled(self) -> None:
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.planner_router_mode == "disabled"

    def test_threshold_defaults_to_0_7(self) -> None:
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.planner_router_haiku_confidence_threshold == pytest.approx(0.7)

    def test_timeout_defaults_to_1500_ms(self) -> None:
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.planner_router_classifier_timeout_ms == 1500


class TestEnvVarParsing:
    def test_morphic_planner_router_env_enables(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MORPHIC_PLANNER_ROUTER", "enabled")
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.planner_router_mode == "enabled"

    def test_morphic_planner_router_env_disabled_explicit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MORPHIC_PLANNER_ROUTER", "disabled")
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.planner_router_mode == "disabled"

    def test_invalid_mode_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MORPHIC_PLANNER_ROUTER", "maybe")
        with pytest.raises(Exception):  # pydantic ValidationError
            Settings(_env_file=None)  # type: ignore[call-arg]

    def test_threshold_env_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(
            "MORPHIC_PLANNER_ROUTER_HAIKU_CONFIDENCE_THRESHOLD", "0.85"
        )
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.planner_router_haiku_confidence_threshold == pytest.approx(0.85)

    def test_timeout_env_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MORPHIC_PLANNER_ROUTER_CLASSIFIER_TIMEOUT_MS", "750")
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.planner_router_classifier_timeout_ms == 750
