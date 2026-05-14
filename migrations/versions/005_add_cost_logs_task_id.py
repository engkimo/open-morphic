"""005 add task_id column to cost_logs

Revision ID: 005_cost_logs_task_id
Revises: 004_exec_affinity_state
Create Date: 2026-05-14

TD-189 step 3: per-task cache_hit_rate aggregation needs cost_logs.task_id
so PgCostRepository.get_cache_hit_rate_for_task can group records by task.
Nullable so existing rows remain valid.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "005_cost_logs_task_id"
down_revision = "004_exec_affinity_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cost_logs",
        sa.Column("task_id", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_cost_logs_task_id",
        "cost_logs",
        ["task_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_cost_logs_task_id", table_name="cost_logs")
    op.drop_column("cost_logs", "task_id")
