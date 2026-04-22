"""004 add execution record, agent affinity, shared task state tables

Revision ID: 004_exec_affinity_state
Revises: 003_fractal_learning
Create Date: 2026-03-26

Sprint 17.1: Persist ExecutionRecord, AgentAffinityScore, SharedTaskState to PG.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "004_exec_affinity_state"
down_revision = "003_fractal_learning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- execution_records --
    op.create_table(
        "execution_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", sa.String(255), nullable=False),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column("goal", sa.Text(), server_default="", nullable=False),
        sa.Column("engine_used", sa.String(50), nullable=False),
        sa.Column("model_used", sa.String(100), server_default="", nullable=False),
        sa.Column("success", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "cost_usd",
            sa.Numeric(10, 6),
            server_default="0",
            nullable=False,
        ),
        sa.Column("duration_seconds", sa.Float(), server_default="0", nullable=False),
        sa.Column("cache_hit_rate", sa.Float(), server_default="0", nullable=False),
        sa.Column("user_rating", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_execution_records_created_at",
        "execution_records",
        [sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_execution_records_task_type",
        "execution_records",
        ["task_type"],
    )
    op.create_index(
        "ix_execution_records_engine_used",
        "execution_records",
        ["engine_used"],
    )

    # -- agent_affinity_scores --
    op.create_table(
        "agent_affinity_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("engine", sa.String(50), nullable=False),
        sa.Column("topic", sa.String(255), nullable=False),
        sa.Column("familiarity", sa.Float(), server_default="0", nullable=False),
        sa.Column("recency", sa.Float(), server_default="0", nullable=False),
        sa.Column("success_rate", sa.Float(), server_default="0", nullable=False),
        sa.Column("cost_efficiency", sa.Float(), server_default="0", nullable=False),
        sa.Column("sample_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_used", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("engine", "topic", name="uq_affinity_engine_topic"),
    )

    # -- shared_task_states --
    op.create_table(
        "shared_task_states",
        sa.Column("task_id", sa.String(255), primary_key=True),
        sa.Column("decisions", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("artifacts", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("blockers", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("agent_history", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_shared_task_states_updated_at",
        "shared_task_states",
        [sa.text("updated_at DESC")],
    )


def downgrade() -> None:
    op.drop_table("shared_task_states")
    op.drop_table("agent_affinity_scores")
    op.drop_table("execution_records")
