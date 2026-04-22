"""Tests for domain/services/forgetting_curve.py — pure math, no I/O."""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest

from domain.services.forgetting_curve import ForgettingCurve


class TestRetentionScore:
    """R = e^(-t/S) where S = 1.0 + access_count*0.5 + importance_score*2.0"""

    def test_zero_elapsed_returns_one(self) -> None:
        """No time elapsed → perfect retention."""
        score = ForgettingCurve.retention_score(
            access_count=1, importance_score=0.5, hours_elapsed=0.0
        )
        assert score == pytest.approx(1.0)

    def test_known_values(self) -> None:
        """Verify against hand-computed value.

        access_count=1, importance=0.5, hours=24
        S = 1.0 + 1*0.5 + 0.5*2.0 = 2.5
        t = 24 / (S * 24) = 24 / 60 = 0.4
        R = e^(-0.4) ≈ 0.6703
        """
        score = ForgettingCurve.retention_score(
            access_count=1, importance_score=0.5, hours_elapsed=24.0
        )
        expected = math.exp(-24.0 / (2.5 * 24))
        assert score == pytest.approx(expected, rel=1e-6)

    def test_high_access_count_slows_decay(self) -> None:
        """Many accesses → higher stability → slower decay."""
        low_access = ForgettingCurve.retention_score(
            access_count=1, importance_score=0.5, hours_elapsed=48.0
        )
        high_access = ForgettingCurve.retention_score(
            access_count=10, importance_score=0.5, hours_elapsed=48.0
        )
        assert high_access > low_access

    def test_high_importance_slows_decay(self) -> None:
        """High importance → higher stability → slower decay."""
        low_imp = ForgettingCurve.retention_score(
            access_count=1, importance_score=0.0, hours_elapsed=48.0
        )
        high_imp = ForgettingCurve.retention_score(
            access_count=1, importance_score=1.0, hours_elapsed=48.0
        )
        assert high_imp > low_imp

    def test_very_old_approaches_zero(self) -> None:
        """Extremely old → retention ≈ 0.0."""
        score = ForgettingCurve.retention_score(
            access_count=1, importance_score=0.0, hours_elapsed=10000.0
        )
        assert score < 0.01

    def test_score_always_between_zero_and_one(self) -> None:
        """Score is always in [0, 1] for valid inputs."""
        for ac in [1, 5, 50]:
            for imp in [0.0, 0.5, 1.0]:
                for hrs in [0.0, 1.0, 100.0, 5000.0]:
                    s = ForgettingCurve.retention_score(ac, imp, hrs)
                    assert 0.0 <= s <= 1.0


class TestIsExpired:
    def test_fresh_entry_not_expired(self) -> None:
        """Just created → score ~1.0 → not expired."""
        assert not ForgettingCurve.is_expired(
            access_count=1, importance_score=0.5, hours_elapsed=0.0
        )

    def test_old_entry_expired(self) -> None:
        """Very old, low importance → expired."""
        assert ForgettingCurve.is_expired(access_count=1, importance_score=0.0, hours_elapsed=500.0)

    def test_boundary_exactly_threshold_not_expired(self) -> None:
        """Score exactly at threshold → NOT expired (strict <)."""
        # S = 2.5, R = e^(-t/(2.5*24)) = 0.3 → t = -ln(0.3) * 60
        hours = -math.log(0.3) * (2.5 * 24)
        assert not ForgettingCurve.is_expired(
            access_count=1, importance_score=0.5, hours_elapsed=hours, threshold=0.3
        )

    def test_boundary_just_past_threshold(self) -> None:
        """Score slightly below threshold → expired."""
        hours = -math.log(0.3) * (2.5 * 24) + 1.0  # 1 hour past boundary
        assert ForgettingCurve.is_expired(
            access_count=1, importance_score=0.5, hours_elapsed=hours, threshold=0.3
        )

    def test_custom_threshold(self) -> None:
        """Higher threshold → more entries expire."""
        hours = 24.0
        expired_low = ForgettingCurve.is_expired(
            access_count=1, importance_score=0.5, hours_elapsed=hours, threshold=0.3
        )
        expired_high = ForgettingCurve.is_expired(
            access_count=1, importance_score=0.5, hours_elapsed=hours, threshold=0.9
        )
        # With threshold=0.9, more likely to be expired
        assert expired_high or not expired_low  # high threshold ≥ low threshold expiry


class TestHoursSince:
    def test_recent(self) -> None:
        """1 hour ago → ~1.0."""
        t = datetime.now() - timedelta(hours=1)
        h = ForgettingCurve.hours_since(t)
        assert 0.9 < h < 1.2  # allow small timing variance

    def test_one_day_ago(self) -> None:
        t = datetime.now() - timedelta(days=1)
        h = ForgettingCurve.hours_since(t)
        assert 23.9 < h < 24.2

    def test_just_now(self) -> None:
        """Now → ~0.0."""
        h = ForgettingCurve.hours_since(datetime.now())
        assert h < 0.01
