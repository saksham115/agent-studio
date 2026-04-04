import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, ForeignKey, Enum, func
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import Organization, User
    from app.models.knowledge_base import KBDocument, KBStructuredSource
    from app.models.action import Action
    from app.models.state import State
    from app.models.channel import Channel
    from app.models.guardrail import Guardrail
    from app.models.conversation import Conversation


class AgentStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    persona: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[AgentStatus] = mapped_column(
        Enum(AgentStatus, name="agent_status_enum"),
        nullable=False,
        default=AgentStatus.DRAFT,
    )
    languages: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(10)), nullable=True, default=list
    )
    model_config_json: Mapped[dict | None] = mapped_column(
        "model_config", JSONB, nullable=True
    )
    welcome_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    fallback_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalation_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_turns: Mapped[int | None] = mapped_column(nullable=True, default=50)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_version: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    organization: Mapped["Organization"] = relationship("Organization", back_populates="agents")
    creator: Mapped["User | None"] = relationship("User", foreign_keys=[created_by])
    kb_documents: Mapped[list["KBDocument"]] = relationship("KBDocument", back_populates="agent", cascade="all, delete-orphan")
    kb_structured_sources: Mapped[list["KBStructuredSource"]] = relationship("KBStructuredSource", back_populates="agent", cascade="all, delete-orphan")
    actions: Mapped[list["Action"]] = relationship("Action", back_populates="agent", cascade="all, delete-orphan")
    states: Mapped[list["State"]] = relationship("State", back_populates="agent", cascade="all, delete-orphan")
    channels: Mapped[list["Channel"]] = relationship("Channel", back_populates="agent", cascade="all, delete-orphan")
    guardrails: Mapped[list["Guardrail"]] = relationship("Guardrail", back_populates="agent", cascade="all, delete-orphan")
    conversations: Mapped[list["Conversation"]] = relationship("Conversation", back_populates="agent", cascade="all, delete-orphan")
