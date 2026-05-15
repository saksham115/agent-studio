"""Merge alembic heads — memory + state-turn-tracking.

The ``memory`` and ``state-diagram`` branches each forked from ``003`` and
added independent migrations:

- ``004_state_turn_tracking``  (state-diagram: state_entered_at + state_turn_count)
- ``004_add_end_users``        (memory: end_users table + Conversation.end_user_id)
- ``005_drop_mem0_tables``     (memory)
- ``006_add_memory_tracking_columns`` (memory)

When the branches merged, alembic ended up with two heads:
``004_state_turn_tracking`` and ``006_add_memory_tracking_columns``. This
is a structural merge migration — no schema change — that re-converges
them into a single linear history.

Revision ID: 007_merge_memory_and_state_heads
Revises: 004_state_turn_tracking, 006_add_memory_tracking_columns
Create Date: 2026-05-11
"""

revision = "007_merge_memory_and_state_heads"
down_revision = ("004_state_turn_tracking", "006_add_memory_tracking_columns")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No schema work — pure head merge.
    pass


def downgrade() -> None:
    # Down would re-fork the history; intentionally a no-op. To roll back,
    # downgrade each head separately on the appropriate branch.
    pass
