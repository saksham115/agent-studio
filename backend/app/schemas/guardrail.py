import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class GuardrailCreate(BaseModel):
    """Schema for creating a new guardrail."""
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    guardrail_type: str = Field(..., pattern="^(input|output|topic|compliance|pii|custom)$")
    rule: str = Field(..., min_length=1)
    action: str = Field(default="block", pattern="^(block|warn|redirect|log)$")
    action_config: dict | None = None
    priority: int = Field(default=0, ge=0)
    is_active: bool = True


class GuardrailUpdate(BaseModel):
    """Schema for updating an existing guardrail."""
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    guardrail_type: str | None = Field(default=None, pattern="^(input|output|topic|compliance|pii|custom)$")
    rule: str | None = Field(default=None, min_length=1)
    action: str | None = Field(default=None, pattern="^(block|warn|redirect|log)$")
    action_config: dict | None = None
    priority: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class GuardrailResponse(BaseModel):
    """Response schema for a guardrail."""
    id: uuid.UUID
    agent_id: uuid.UUID
    name: str
    description: str | None = None
    guardrail_type: str
    rule: str
    action: str
    action_config: dict | None = None
    priority: int
    is_active: bool
    is_auto_generated: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GuardrailListResponse(BaseModel):
    """List of guardrails for an agent."""
    items: list[GuardrailResponse]
    total: int


class GuardrailGenerateRequest(BaseModel):
    """Request to auto-generate guardrails for an agent based on its configuration."""
    guardrail_types: list[str] | None = Field(
        default=None,
        description="Specific guardrail types to generate. If None, generates all recommended types.",
    )
    include_compliance: bool = Field(
        default=True,
        description="Whether to include IRDAI compliance guardrails.",
    )
