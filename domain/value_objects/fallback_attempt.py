"""FallbackAttempt — immutable record of a single engine attempt during fallback."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class FallbackAttempt(BaseModel):
    """Record of one engine attempt in a fallback chain.

    Immutable value object — created once per engine trial during routing.
    """

    model_config = ConfigDict(strict=True, frozen=True)

    engine: str = Field(min_length=1)
    attempted: bool = True
    skip_reason: str | None = None
    error: str | None = None
    duration_seconds: float = Field(default=0.0, ge=0.0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
