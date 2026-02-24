"""CostLog model — tracks all LLM API costs."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CostLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Per-call cost tracking. Ollama calls have cost_usd=0, is_local=True."""

    __tablename__ = "cost_logs"

    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    is_local: Mapped[bool] = mapped_column(Boolean, default=False)
