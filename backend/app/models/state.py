import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.agent import Agent


class State(Base):
    __tablename__ = "states"
    # Mirrors the `uq_states_agent_name` index added in alembic 004. The
    # __transition_to_state tool dispatches by state name within an agent;
    # without uniqueness two same-named states would silently route to
    # whichever the DB returned first.
    __table_args__ = (
        UniqueConstraint("agent_id", "name", name="uq_states_agent_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_initial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_terminal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    position_x: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position_y: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    agent: Mapped["Agent"] = relationship("Agent", back_populates="states")
    outgoing_transitions: Mapped[list["Transition"]] = relationship(
        "Transition",
        foreign_keys="Transition.from_state_id",
        back_populates="from_state",
        cascade="all, delete-orphan",
        # Ascending priority: lower priority number = higher precedence.
        # transition_picker.force_pick_transition relies on candidates[0]
        # being the highest-priority outgoing transition for its
        # deterministic fallback when the LLM returns an invalid pick.
        order_by="Transition.priority",
    )
    incoming_transitions: Mapped[list["Transition"]] = relationship(
        "Transition",
        foreign_keys="Transition.to_state_id",
        back_populates="to_state",
        cascade="all, delete-orphan",
    )


class Transition(Base):
    __tablename__ = "transitions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    from_state_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("states.id", ondelete="CASCADE"), nullable=False
    )
    to_state_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("states.id", ondelete="CASCADE"), nullable=False
    )
    condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    from_state: Mapped["State"] = relationship(
        "State", foreign_keys=[from_state_id], back_populates="outgoing_transitions"
    )
    to_state: Mapped["State"] = relationship(
        "State", foreign_keys=[to_state_id], back_populates="incoming_transitions"
    )
