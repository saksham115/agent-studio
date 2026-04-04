import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, ForeignKey, Enum, Boolean, Integer, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.agent import Agent


class GuardrailType(str, enum.Enum):
    INPUT = "input"
    OUTPUT = "output"
    TOPIC = "topic"
    COMPLIANCE = "compliance"
    PII = "pii"
    CUSTOM = "custom"


class GuardrailAction(str, enum.Enum):
    BLOCK = "block"
    WARN = "warn"
    REDIRECT = "redirect"
    LOG = "log"


class Guardrail(Base):
    __tablename__ = "guardrails"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    guardrail_type: Mapped[GuardrailType] = mapped_column(
        Enum(GuardrailType, values_callable=lambda x: [e.value for e in x], name="guardrail_type_enum"), nullable=False
    )
    rule: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[GuardrailAction] = mapped_column(
        Enum(GuardrailAction, values_callable=lambda x: [e.value for e in x], name="guardrail_action_enum"),
        nullable=False,
        default=GuardrailAction.BLOCK,
    )
    action_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_auto_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    agent: Mapped["Agent"] = relationship("Agent", back_populates="guardrails")
