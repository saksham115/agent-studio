"""EndUser model — the identity layer that binds callers to Agno user_ids.

Agno's MemoryManager keys facts on a string ``user_id`` but doesn't manage
who that user IS — that mapping (phone number / SIP URI / chatbot session
ID → stable UUID) is ours.
``EndUser.id`` is the UUID we hand to Agno's memory APIs; Agno stores its
own facts keyed on it.

Memory storage itself lives in Agno's table ``agno_memories`` (plus an
auxiliary ``agno_schema_versions``), created lazily by ``AsyncPostgresDb``
on first use in our shared Postgres. We don't model those here.

Identity is per-agent: same phone number calling Agent A and Agent B
produces two distinct ``EndUser`` rows. Cross-agent unification is out of
scope (different contexts, different data tenancy).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.conversation import Conversation


class EndUser(Base):
    """A caller / chatbot session bound to a stable UUID for memory keying.

    Two identifier dimensions, both nullable, exactly one expected per row:

    - ``phone_number`` — E.164 normalized; populated when the caller has
      a real phone number (PSTN inbound, WhatsApp).
    - ``external_id`` — non-phone identifier; populated for chatbot
      sessions (caller's ``user_id`` from the chatbot client) and SIP
      Endpoint demos (the SIP URI from a Plivo Endpoint, since
      ``phonenumbers`` won't parse it).

    Partial unique indexes (created in alembic 004) enforce per-agent
    uniqueness on each populated dimension separately.
    """

    __tablename__ = "end_users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )

    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    total_conversations: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )

    # Forward-ref string to sidestep circular import with Conversation.
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation",
        back_populates="end_user",
        lazy="dynamic",  # queryable; never auto-load all of a busy user's calls
    )
