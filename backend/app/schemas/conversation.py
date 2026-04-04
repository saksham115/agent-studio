import uuid
from datetime import datetime

from pydantic import BaseModel


class MessageResponse(BaseModel):
    """Response schema for a single message."""
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    content_type: str
    token_count: int | None = None
    latency_ms: int | None = None
    model_used: str | None = None
    tool_calls: dict | None = None
    metadata_json: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationSummary(BaseModel):
    """Brief summary of a conversation for list views."""
    id: uuid.UUID
    agent_id: uuid.UUID
    agent_name: str | None = None
    external_user_id: str | None = None
    external_user_phone: str | None = None
    external_user_name: str | None = None
    status: str
    message_count: int
    language: str | None = None
    sentiment_score: float | None = None
    started_at: datetime
    ended_at: datetime | None = None

    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    """Paginated list of conversations."""
    items: list[ConversationSummary]
    total: int
    page: int
    page_size: int
    total_pages: int


class ConversationDetailResponse(BaseModel):
    """Full conversation with messages."""
    id: uuid.UUID
    agent_id: uuid.UUID
    agent_name: str | None = None
    channel_id: uuid.UUID | None = None
    external_user_id: str | None = None
    external_user_phone: str | None = None
    external_user_name: str | None = None
    status: str
    current_state_id: uuid.UUID | None = None
    context: dict | None = None
    message_count: int
    language: str | None = None
    sentiment_score: float | None = None
    started_at: datetime
    ended_at: datetime | None = None
    messages: list[MessageResponse]

    model_config = {"from_attributes": True}


class DashboardStatsResponse(BaseModel):
    """Dashboard overview statistics."""
    total_agents: int
    active_agents: int
    total_conversations: int
    active_conversations: int
    total_messages: int
    avg_messages_per_conversation: float
    avg_sentiment_score: float | None = None
    conversations_by_channel: dict[str, int]
    conversations_by_status: dict[str, int]
    top_agents: list[dict]


class AgentStatsResponse(BaseModel):
    """Statistics for a specific agent."""
    agent_id: uuid.UUID
    agent_name: str
    total_conversations: int
    active_conversations: int
    total_messages: int
    avg_messages_per_conversation: float
    avg_response_latency_ms: float | None = None
    avg_sentiment_score: float | None = None
    guardrail_triggers_count: int
    action_executions_count: int
    conversations_by_day: list[dict]
    conversations_by_status: dict[str, int]
    top_states: list[dict]
