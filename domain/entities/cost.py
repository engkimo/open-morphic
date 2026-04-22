"""Cost entity — LLM + engine cost tracking. Pure domain."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class CostRecord(BaseModel):
    """A single LLM or engine call cost record.

    For LLM calls: model is the LLM model name, tokens are populated.
    For engine calls: engine_type is set, tokens may be zero.
    """

    model_config = ConfigDict(strict=True)

    model: str = Field(min_length=1)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    cached_tokens: int = Field(default=0, ge=0)
    is_local: bool = False
    engine_type: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)

    @classmethod
    def from_engine_result(
        cls,
        engine_type: str,
        model_used: str | None,
        cost_usd: float,
        is_local: bool = False,
    ) -> CostRecord:
        """Create a CostRecord from an agent engine execution result."""
        return cls(
            model=model_used or f"engine/{engine_type}",
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=cost_usd,
            cached_tokens=0,
            is_local=is_local,
            engine_type=engine_type,
            timestamp=datetime.now(UTC),
        )
