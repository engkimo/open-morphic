"""ForgettingCurve — Ebbinghaus-inspired retention scoring.

Pure domain service: no I/O, no external deps beyond stdlib math.
Determines whether L2 semantic memories should expire based on
access frequency, importance, and elapsed time.

Formula: R = e^(-t/S)
  t = hours_elapsed / (S * 24)   (normalized to days)
  S = 1.0 + access_count * 0.5 + importance_score * 2.0  (stability)
"""

from __future__ import annotations

import math
from datetime import datetime


class ForgettingCurve:
    """Static methods for retention scoring — no state, pure functions."""

    @staticmethod
    def retention_score(
        access_count: int,
        importance_score: float,
        hours_elapsed: float,
    ) -> float:
        """Compute retention score R = e^(-t / (S * 24)).

        Args:
            access_count: Number of times the memory was accessed (>= 1).
            importance_score: LLM-assessed importance in [0, 1].
            hours_elapsed: Hours since last access.

        Returns:
            Retention score in [0, 1]. 1.0 = perfect retention.
        """
        stability = 1.0 + access_count * 0.5 + importance_score * 2.0
        return math.exp(-hours_elapsed / (stability * 24))

    @staticmethod
    def is_expired(
        access_count: int,
        importance_score: float,
        hours_elapsed: float,
        threshold: float = 0.3,
    ) -> bool:
        """Return True if retention score is below threshold (strictly less)."""
        score = ForgettingCurve.retention_score(access_count, importance_score, hours_elapsed)
        return score < threshold

    @staticmethod
    def hours_since(last_accessed: datetime) -> float:
        """Compute hours elapsed since a given datetime until now."""
        delta = datetime.now() - last_accessed
        return delta.total_seconds() / 3600.0
