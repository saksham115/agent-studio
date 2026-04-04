import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class StateNode(BaseModel):
    """A single state node in the state diagram."""
    id: str = Field(..., description="Temporary or persisted UUID for the node")
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    instructions: str | None = None
    is_initial: bool = False
    is_terminal: bool = False
    position_x: int | None = None
    position_y: int | None = None
    metadata: dict | None = None


class TransitionEdge(BaseModel):
    """A single transition edge in the state diagram."""
    id: str = Field(..., description="Temporary or persisted UUID for the edge")
    from_state_id: str
    to_state_id: str
    condition: str | None = None
    description: str | None = None
    priority: int = 0
    metadata: dict | None = None


class StateDiagramSave(BaseModel):
    """Schema for saving the entire state diagram (nodes + edges)."""
    nodes: list[StateNode]
    edges: list[TransitionEdge]


class StateResponse(BaseModel):
    """Response schema for a single state."""
    id: uuid.UUID
    agent_id: uuid.UUID
    name: str
    description: str | None = None
    instructions: str | None = None
    is_initial: bool
    is_terminal: bool
    position_x: int | None = None
    position_y: int | None = None
    metadata_json: dict | None = Field(default=None, serialization_alias="metadata")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class TransitionResponse(BaseModel):
    """Response schema for a single transition."""
    id: uuid.UUID
    agent_id: uuid.UUID
    from_state_id: uuid.UUID
    to_state_id: uuid.UUID
    condition: str | None = None
    description: str | None = None
    priority: int
    metadata_json: dict | None = Field(default=None, serialization_alias="metadata")
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class StateDiagramResponse(BaseModel):
    """Response schema for the full state diagram."""
    nodes: list[StateResponse]
    edges: list[TransitionResponse]
