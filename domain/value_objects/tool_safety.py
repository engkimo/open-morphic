"""SafetyTier — Tool safety classification for marketplace."""

from __future__ import annotations

from enum import IntEnum


class SafetyTier(IntEnum):
    """Safety classification for tool candidates.

    Higher value = more trusted.
    """

    UNSAFE = 0
    EXPERIMENTAL = 1
    COMMUNITY = 2
    VERIFIED = 3
