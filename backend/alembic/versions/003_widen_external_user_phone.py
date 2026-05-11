"""Widen Conversation.external_user_phone for SIP URIs.

The Plivo migration (Exotel → Plivo) introduced SIP Endpoint demos where
``From`` / ``To`` arrive as full SIP URIs like
``sip:agentstudio10146403989399950706519@phone.plivo.com`` (51 chars). The
original VARCHAR(20) column rejected these, causing
``StringDataRightTruncationError`` and a rolled-back transaction that
prevented the inbound call from ever connecting.

VARCHAR(64) accommodates SIP URIs with comfortable headroom while staying
narrow enough to keep the index small.

Revision ID: 003_widen_external_user_phone
Revises: 002_trim_action_type
Create Date: 2026-04-30
"""

from alembic import op
import sqlalchemy as sa


revision = "003_widen_external_user_phone"
down_revision = "002_trim_action_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "conversations",
        "external_user_phone",
        type_=sa.String(length=64),
        existing_type=sa.String(length=20),
        existing_nullable=True,
    )


def downgrade() -> None:
    # NOTE: any rows whose external_user_phone exceeds 20 chars (e.g. SIP URIs
    # from the Plivo demo) will be truncated by Postgres on this downgrade.
    # Those rows are useful only for forensics; truncation doesn't break any
    # active call flow. If you need to preserve them, dump first.
    op.alter_column(
        "conversations",
        "external_user_phone",
        type_=sa.String(length=20),
        existing_type=sa.String(length=64),
        existing_nullable=True,
    )
