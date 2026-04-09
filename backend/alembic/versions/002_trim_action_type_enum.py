"""Trim action_type_enum to api_call and data_lookup only.

Removes the four scaffolded action types (tool_call, handoff, send_message,
custom) from the action_type_enum. Their handlers were stub no-ops, so any
existing rows using them are deleted on upgrade.

Revision ID: 002_trim_action_type
Revises: 001_initial
Create Date: 2026-04-09
"""

from alembic import op


revision = "002_trim_action_type"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop any rows that still use the removed types — they were stubs
    # and never executed real work, so removing them is non-destructive.
    op.execute(
        "DELETE FROM actions "
        "WHERE action_type IN ('tool_call', 'handoff', 'send_message', 'custom')"
    )

    # Postgres can't drop enum values in place — recreate the enum.
    op.execute("ALTER TYPE action_type_enum RENAME TO action_type_enum_old")
    op.execute("CREATE TYPE action_type_enum AS ENUM ('api_call', 'data_lookup')")
    op.execute(
        "ALTER TABLE actions "
        "ALTER COLUMN action_type TYPE action_type_enum "
        "USING action_type::text::action_type_enum"
    )
    op.execute("DROP TYPE action_type_enum_old")


def downgrade() -> None:
    op.execute("ALTER TYPE action_type_enum RENAME TO action_type_enum_old")
    op.execute(
        "CREATE TYPE action_type_enum AS ENUM "
        "('api_call', 'tool_call', 'handoff', 'data_lookup', 'send_message', 'custom')"
    )
    op.execute(
        "ALTER TABLE actions "
        "ALTER COLUMN action_type TYPE action_type_enum "
        "USING action_type::text::action_type_enum"
    )
    op.execute("DROP TYPE action_type_enum_old")
