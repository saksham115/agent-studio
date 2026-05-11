"""Add per-conversation memory tracking columns + idle-sweep partial index.

Three new columns on ``conversations``:

- ``memory_written_at`` — set only on a successful Agno extraction.
  NULL while pending; permanently set when ``add_memory`` returns True.
- ``last_message_at``  — bumped on every Message INSERT (orchestrator
  co-locates the update with each ``db.add(Message(...))``). Drives the
  idle-sweep predicate for WhatsApp + chatbot since those channels have
  no clean termination signal.
- ``memory_extraction_attempts`` — bounded retry counter (cap from
  ``settings.MEMORY_MAX_EXTRACTION_ATTEMPTS``, default 5). Once a row
  hits the cap, the partial index excludes it — sweep stops retrying.
  Operator reset path: ``reset_memory_attempts.py --conversation-id UUID``.

Plus ``idx_conversations_idle_sweep`` — a partial index on
``(status, last_message_at)`` filtered by the three conditions the
Celery sweep cares about: row is unwritten, end-user-linked, and below
the retry cap. Keeps the sweep scan O(active-unwritten-not-exhausted)
even with millions of historical conversations.

Backfill ``last_message_at`` from ``MAX(messages.created_at)`` so existing
conversations are immediately sweep-eligible (or excluded if they have no
messages — NULL stays NULL).

Revision ID: 006_add_memory_tracking_columns
Revises: 005_drop_mem0_tables
Create Date: 2026-05-11
"""

import sqlalchemy as sa
from alembic import op


revision = "006_add_memory_tracking_columns"
down_revision = "005_drop_mem0_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("memory_written_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "memory_extraction_attempts",
            sa.Integer,
            server_default="0",
            nullable=False,
        ),
    )

    # Backfill last_message_at from the messages table. Conversations with
    # zero messages keep last_message_at = NULL → they won't appear in the
    # idle sweep until a message arrives (correct: nothing to extract yet).
    op.execute(
        """
        UPDATE conversations c
           SET last_message_at = sub.max_created
          FROM (
            SELECT conversation_id, MAX(created_at) AS max_created
              FROM messages
             GROUP BY conversation_id
          ) sub
         WHERE sub.conversation_id = c.id
        """
    )

    # Partial index — keeps the idle-sweep scan tight. The literal `< 5` here
    # must stay in sync with settings.MEMORY_MAX_EXTRACTION_ATTEMPTS; if you
    # change the cap, also bump the index predicate in a follow-up migration.
    op.create_index(
        "idx_conversations_idle_sweep",
        "conversations",
        ["status", "last_message_at"],
        postgresql_where=sa.text(
            "memory_written_at IS NULL "
            "AND end_user_id IS NOT NULL "
            "AND memory_extraction_attempts < 5"
        ),
    )


def downgrade() -> None:
    op.drop_index("idx_conversations_idle_sweep", table_name="conversations")
    op.drop_column("conversations", "memory_extraction_attempts")
    op.drop_column("conversations", "last_message_at")
    op.drop_column("conversations", "memory_written_at")
