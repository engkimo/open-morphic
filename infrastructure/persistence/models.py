"""SQLAlchemy ORM models — Infrastructure layer.

These are NOT domain entities. They are persistence representations.
Mapping between domain entities and ORM models is done in repositories.

Portable: works on both PostgreSQL (JSONB, native UUID) and SQLite (JSON, CHAR(36)).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from infrastructure.persistence.portable_types import GUID, PortableJSON

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None  # type: ignore[assignment, misc]


class Base(DeclarativeBase):
    pass


# ── Task ──


class TaskModel(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("tasks.id"), nullable=True
    )
    depth: Mapped[int] = mapped_column(Integer, default=0)
    metadata_: Mapped[dict] = mapped_column("metadata", PortableJSON, default=dict)
    final_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    children: Mapped[list[TaskModel]] = relationship("TaskModel", back_populates="parent")
    parent: Mapped[TaskModel | None] = relationship(
        "TaskModel", remote_side=[id], back_populates="children"
    )
    executions: Mapped[list[TaskExecutionModel]] = relationship(
        "TaskExecutionModel", back_populates="task"
    )


# ── Task Execution ──


class TaskExecutionModel(Base):
    __tablename__ = "task_executions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tasks.id"), nullable=False
    )
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[TaskModel] = relationship("TaskModel", back_populates="executions")


# ── Memory ──


class MemoryModel(Base):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(384), nullable=True) if Vector else None
    memory_type: Mapped[str] = mapped_column(String(20), nullable=False)
    access_count: Mapped[int] = mapped_column(Integer, default=1)
    importance_score: Mapped[float] = mapped_column(Float, default=0.5)
    metadata_: Mapped[dict] = mapped_column("metadata", PortableJSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_accessed: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── Cost Log ──


class CostLogModel(Base):
    __tablename__ = "cost_logs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    is_local: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Plan ──


class PlanModel(Base):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    steps: Mapped[dict] = mapped_column(PortableJSON, default=list)
    total_estimated_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), default=Decimal("0"),
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("tasks.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ── Fractal Learning ──


class FractalErrorPatternModel(Base):
    __tablename__ = "fractal_error_patterns"
    __table_args__ = (
        UniqueConstraint(
            "goal_fragment",
            "node_description",
            "error_message",
            name="uq_error_pattern",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    goal_fragment: Mapped[str] = mapped_column(Text, nullable=False)
    node_description: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    nesting_level: Mapped[int] = mapped_column(Integer, default=0)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FractalSuccessfulPathModel(Base):
    __tablename__ = "fractal_successful_paths"
    __table_args__ = (
        UniqueConstraint("goal_fragment", "node_descriptions", name="uq_successful_path"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    goal_fragment: Mapped[str] = mapped_column(Text, nullable=False)
    node_descriptions: Mapped[dict] = mapped_column(PortableJSON, nullable=False)
    nesting_level: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    usage_count: Mapped[int] = mapped_column(Integer, default=1)
    first_used: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Execution Record ──


class ExecutionRecordModel(Base):
    __tablename__ = "execution_records"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[str] = mapped_column(String(255), nullable=False)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    goal: Mapped[str] = mapped_column(Text, default="")
    engine_used: Mapped[str] = mapped_column(String(50), nullable=False)
    model_used: Mapped[str] = mapped_column(String(100), default="")
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    cache_hit_rate: Mapped[float] = mapped_column(Float, default=0.0)
    user_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Agent Affinity Score ──


class AgentAffinityScoreModel(Base):
    __tablename__ = "agent_affinity_scores"
    __table_args__ = (UniqueConstraint("engine", "topic", name="uq_affinity_engine_topic"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    engine: Mapped[str] = mapped_column(String(50), nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    familiarity: Mapped[float] = mapped_column(Float, default=0.0)
    recency: Mapped[float] = mapped_column(Float, default=0.0)
    success_rate: Mapped[float] = mapped_column(Float, default=0.0)
    cost_efficiency: Mapped[float] = mapped_column(Float, default=0.0)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ── Shared Task State ──


class SharedTaskStateModel(Base):
    __tablename__ = "shared_task_states"

    task_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    decisions: Mapped[dict] = mapped_column(PortableJSON, default=list)
    artifacts: Mapped[dict] = mapped_column(PortableJSON, default=dict)
    blockers: Mapped[dict] = mapped_column(PortableJSON, default=list)
    agent_history: Mapped[dict] = mapped_column(PortableJSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
