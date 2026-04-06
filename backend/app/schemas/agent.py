import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AgentCreate(BaseModel):
    """Schema for creating a new agent."""
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    system_prompt: str | None = None
    persona: str | None = None
    languages: list[str] | None = Field(default=["en"], max_length=20)
    welcome_message: str | None = None
    fallback_message: str | None = None
    escalation_message: str | None = None
    max_turns: int | None = Field(default=50, ge=1, le=500)
    model_config_data: dict | None = Field(default=None, alias="model_config")


class AgentUpdate(BaseModel):
    """Schema for updating an existing agent."""
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    system_prompt: str | None = None
    persona: str | None = None
    languages: list[str] | None = None
    welcome_message: str | None = None
    fallback_message: str | None = None
    escalation_message: str | None = None
    max_turns: int | None = Field(default=None, ge=1, le=500)
    model_config_data: dict | None = Field(default=None, alias="model_config")


class AgentResponse(BaseModel):
    """Schema for a single agent response."""
    id: uuid.UUID
    org_id: uuid.UUID
    created_by: uuid.UUID | None = None
    name: str
    description: str | None = None
    system_prompt: str | None = None
    persona: str | None = None
    status: str
    languages: list[str] | None = None
    model_config_json: dict | None = Field(default=None, serialization_alias="model_config")
    welcome_message: str | None = None
    fallback_message: str | None = None
    escalation_message: str | None = None
    max_turns: int | None = None
    published_at: datetime | None = None
    published_version: int | None = None
    created_at: datetime
    updated_at: datetime
    conversation_count: int = 0

    model_config = {"from_attributes": True, "populate_by_name": True}


class AgentListResponse(BaseModel):
    """Paginated list of agents."""
    items: list[AgentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class AgentPublishResponse(BaseModel):
    """Response after publishing an agent."""
    id: uuid.UUID
    status: str
    published_at: datetime
    published_version: int
