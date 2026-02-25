"""Cost entity — LLM cost tracking. Pure domain."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CostRecord(BaseModel):
    """A single LLM call cost record."""

    model_config = ConfigDict(strict=True)

    model: str = Field(min_length=1)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    cached_tokens: int = Field(default=0, ge=0)
    is_local: bool = False
    timestamp: datetime = Field(default_factory=datetime.now)
