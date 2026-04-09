import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ActionCreate(BaseModel):
    """Schema for creating a new action."""
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    action_type: str = Field(..., pattern="^(api_call|data_lookup)$")
    config: dict = Field(default_factory=dict)
    input_params: dict | None = None
    output_schema: dict | None = None
    requires_confirmation: bool = False


class ActionUpdate(BaseModel):
    """Schema for updating an existing action."""
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    action_type: str | None = Field(default=None, pattern="^(api_call|data_lookup)$")
    config: dict | None = None
    input_params: dict | None = None
    output_schema: dict | None = None
    requires_confirmation: bool | None = None
    is_active: bool | None = None


class ActionResponse(BaseModel):
    """Response schema for an action."""
    id: uuid.UUID
    agent_id: uuid.UUID
    name: str
    description: str | None = None
    action_type: str
    config: dict
    input_params: dict | None = None
    output_schema: dict | None = None
    requires_confirmation: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ActionListResponse(BaseModel):
    """List of actions for an agent."""
    items: list[ActionResponse]
    total: int
