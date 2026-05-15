"""Drop mem0's tables — replaced by Agno's memory subsystem.

Mem0 v2 created ``agent_studio_memory`` and ``agent_studio_memory_history``
lazily via its pgvector backend. After this migration, Agno's
``AsyncPostgresDb`` lazy-creates its own ``agno_memories`` schema on first use.

Mentor-approved wipe (2026-05-11) — dev-only memory data, no production
memory to preserve.

Revision ID: 005_drop_mem0_tables
Revises: 004_add_end_users
Create Date: 2026-05-11
"""

from alembic import op


revision = "005_drop_mem0_tables"
down_revision = "004_add_end_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_studio_memory CASCADE")
    op.execute("DROP TABLE IF EXISTS agent_studio_memory_history CASCADE")


def downgrade() -> None:
    # mem0 lazy-recreates these on first add() if rolled back to the mem0
    # wrapper. Intentionally no recreation here — the down migration is a
    # stub; rollback is a full revert of the Agno migration commits.
    pass
