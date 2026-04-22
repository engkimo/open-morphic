"""003 add fractal learning tables

Revision ID: 003_fractal_learning
Revises: 002_embedding
Create Date: 2026-03-26

Adds fractal_error_patterns and fractal_successful_paths tables
for persisting learning data from the Fractal Engine (Sprint 16.2).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "003_fractal_learning"
down_revision = "002_embedding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- fractal_error_patterns --
    op.create_table(
        "fractal_error_patterns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("goal_fragment", sa.Text(), nullable=False),
        sa.Column("node_description", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("nesting_level", sa.Integer(), server_default="0", nullable=False),
        sa.Column("occurrence_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "first_seen",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "goal_fragment",
            "node_description",
            "error_message",
            name="uq_error_pattern",
        ),
    )
    op.create_index(
        "ix_error_patterns_occurrence_count",
        "fractal_error_patterns",
        [sa.text("occurrence_count DESC")],
    )

    # -- fractal_successful_paths --
    op.create_table(
        "fractal_successful_paths",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("goal_fragment", sa.Text(), nullable=False),
        sa.Column("node_descriptions", postgresql.JSONB(), nullable=False),
        sa.Column("nesting_level", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "total_cost_usd",
            sa.Numeric(10, 6),
            server_default="0",
            nullable=False,
        ),
        sa.Column("usage_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "first_used",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_used",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "goal_fragment",
            "node_descriptions",
            name="uq_successful_path",
        ),
    )
    op.create_index(
        "ix_successful_paths_usage_count",
        "fractal_successful_paths",
        [sa.text("usage_count DESC")],
    )


def downgrade() -> None:
    op.drop_table("fractal_successful_paths")
    op.drop_table("fractal_error_patterns")
