import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ChannelConfigUpdate(BaseModel):
    """Schema for updating channel configuration."""
    config: dict = Field(default_factory=dict)
    is_active: bool | None = None
    phone_number: str | None = Field(default=None, max_length=20)
    webhook_url: str | None = Field(default=None, max_length=1024)


class ChannelResponse(BaseModel):
    """Response schema for a channel."""
    id: uuid.UUID
    agent_id: uuid.UUID
    channel_type: str
    status: str
    config: dict
    is_active: bool
    phone_number: str | None = None
    webhook_url: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChannelListResponse(BaseModel):
    """List of channels for an agent."""
    items: list[ChannelResponse]
    total: int
