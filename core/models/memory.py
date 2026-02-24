"""Memory model — semantic memory with pgvector embeddings."""

from __future__ import annotations

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None  # type: ignore[assignment, misc]


class Memory(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Semantic memory entry with vector embedding for similarity search."""

    __tablename__ = "memories"

    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(1536), nullable=True) if Vector else None
    memory_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # l2_semantic | l4_cold
    access_count: Mapped[int] = mapped_column(Integer, default=1)
    importance_score: Mapped[float] = mapped_column(Float, default=0.5)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
