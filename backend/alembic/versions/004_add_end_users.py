"""Add end_users table + Conversation.end_user_id FK.

The identity layer for end-user memory (mem0 stores facts keyed on a
stable UUID we mint). EndUser binds callers — phone numbers, SIP URIs,
chatbot session IDs — to that UUID so consecutive calls from the same
person resolve to the same memory namespace.

Two identifier dimensions on the same row, each with its own per-agent
unique partial index. Exactly one is expected to be populated per row:
- ``phone_number`` — for parseable phone numbers (E.164 normalized)
- ``external_id`` — for chatbot user_ids and SIP URIs (anything else)

NOTE: this migration does NOT touch mem0's tables (``agent_studio_memory``,
``agent_studio_memory_history``). mem0 owns those and creates them lazily
on first ``add()`` via its pgvector backend. Memory data lives in mem0's
schema; this migration only manages our identity layer + FK.

The composite ``idx_conversations_end_user_status`` covers both single-column
queries on ``end_user_id`` (Postgres uses leading-prefix B-tree match) and
the WhatsApp/voice "find ACTIVE conversation for this end-user" lookup.

Revision ID: 004_add_end_users
Revises: 003_widen_external_user_phone
Create Date: 2026-05-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision = "004_add_end_users"
down_revision = "003_widen_external_user_phone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. end_users table
    op.create_table(
        "end_users",
        sa.Column(
            "id", UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "agent_id", UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("phone_number", sa.String(20), nullable=True),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column(
            "first_seen_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "total_conversations", sa.Integer,
            server_default="0", nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )

    # 2. Per-agent unique partial indexes — one EndUser per (agent, phone) and
    #    per (agent, external_id), but NULL identifiers don't conflict.
    op.create_index(
        "uq_end_users_agent_phone",
        "end_users",
        ["agent_id", "phone_number"],
        unique=True,
        postgresql_where=sa.text("phone_number IS NOT NULL"),
    )
    op.create_index(
        "uq_end_users_agent_external",
        "end_users",
        ["agent_id", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )

    # 3. FK column on conversations. NO column-level index — the composite
    #    below covers leading-prefix queries on end_user_id.
    op.add_column(
        "conversations",
        sa.Column(
            "end_user_id", UUID(as_uuid=True),
            sa.ForeignKey("end_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # 4. Composite index for the active-conversation lookup pattern used by
    #    WhatsApp / voice / chatbot. Hits both the FK lookup and the
    #    "WHERE end_user_id = X AND status = 'active'" filter cleanly.
    op.create_index(
        "idx_conversations_end_user_status",
        "conversations",
        ["end_user_id", "status", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    # NOTE: this is destructive once the application has run with end_user_id
    # populated — Conversations lose their identity link. mem0's tables
    # (agent_studio_memory*) are NOT touched by this migration; if you want
    # to clear memory storage too, do it manually:
    #     DROP TABLE IF EXISTS agent_studio_memory, agent_studio_memory_history CASCADE;
    op.drop_index("idx_conversations_end_user_status", table_name="conversations")
    op.drop_column("conversations", "end_user_id")
    op.drop_index("uq_end_users_agent_external", table_name="end_users")
    op.drop_index("uq_end_users_agent_phone", table_name="end_users")
    op.drop_table("end_users")
