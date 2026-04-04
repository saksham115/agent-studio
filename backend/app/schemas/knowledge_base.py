import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class KBDocumentResponse(BaseModel):
    """Response schema for a knowledge base document."""
    id: uuid.UUID
    agent_id: uuid.UUID
    filename: str
    source_type: str
    file_size_bytes: int | None = None
    status: str
    chunk_count: int
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KBDocumentListResponse(BaseModel):
    """List of knowledge base documents."""
    items: list[KBDocumentResponse]
    total: int


class KBStructuredSourceCreate(BaseModel):
    """Schema for creating a structured knowledge base source."""
    name: str = Field(..., min_length=1, max_length=255)
    source_type: str = Field(..., pattern="^(api|database|spreadsheet)$")
    connection_config: dict
    query_template: str | None = None
    refresh_interval_minutes: int | None = Field(default=None, ge=1, le=10080)


class KBStructuredSourceUpdate(BaseModel):
    """Schema for updating a structured knowledge base source."""
    name: str | None = Field(default=None, min_length=1, max_length=255)
    connection_config: dict | None = None
    query_template: str | None = None
    refresh_interval_minutes: int | None = Field(default=None, ge=1, le=10080)
    is_active: bool | None = None


class KBStructuredSourceResponse(BaseModel):
    """Response schema for a structured source."""
    id: uuid.UUID
    agent_id: uuid.UUID
    name: str
    source_type: str
    connection_config: dict
    query_template: str | None = None
    refresh_interval_minutes: int | None = None
    is_active: bool
    last_synced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
