"""State turn tracking + states uniqueness constraint.

Adds the per-state turn counter that powers the agent's ``maxTurns``
enforcement and the ``state_entered_at`` anchor that powers the conversation
viewer's State Timeline panel.

Also adds ``UNIQUE(agent_id, name)`` on ``states``: the new
``__transition_to_state`` LLM tool dispatches by state name within an agent.
Without uniqueness, two same-named states in one agent would silently route
to whichever the DB returned first.

Pre-deploy data check (must return zero rows or this migration fails):

    SELECT agent_id, name, COUNT(*)
    FROM states GROUP BY agent_id, name HAVING COUNT(*) > 1;

Revision ID: 004_state_turn_tracking
Revises: 003_widen_external_user_phone
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa


revision = "004_state_turn_tracking"
down_revision = "003_widen_external_user_phone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("state_entered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "state_turn_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_index(
        "uq_states_agent_name",
        "states",
        ["agent_id", "name"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_states_agent_name", table_name="states")
    op.drop_column("conversations", "state_turn_count")
    op.drop_column("conversations", "state_entered_at")
