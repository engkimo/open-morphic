"""002 add embedding column

Revision ID: 002_embedding
Revises: 001_initial
Create Date: 2026-02-26

Adds embedding Vector(384) column to memories table with HNSW index
for cosine distance search. Migrates from the original Vector(1536) definition.
"""

from __future__ import annotations

from alembic import op

revision = "002_embedding"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 001 declared Vector(1536) in ORM but never created the column in migration.
    # Add the actual column with correct dimension (384 for all-minilm).
    op.execute("ALTER TABLE memories ADD COLUMN IF NOT EXISTS embedding vector(384)")

    # HNSW index for cosine distance — faster than IVFFlat for < 1M rows
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_memories_embedding_hnsw "
        "ON memories USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_memories_embedding_hnsw")
    op.execute("ALTER TABLE memories DROP COLUMN IF EXISTS embedding")
