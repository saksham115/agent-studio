"""Public Chatbot API — REST endpoints for customers to interact with deployed agents.

Authentication is via API key (X-API-Key header), not the internal JWT auth.
These endpoints are mounted at /api/v1/chat/{agent_id}/...
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.agent import Agent, AgentStatus
from app.models.channel import ChatbotApiKey
from app.models.conversation import Conversation, ConversationStatus

router = APIRouter()


# --- Schemas ---

class ChatSessionCreate(BaseModel):
    """Request to create a new chat session."""
    user_id: str | None = Field(default=None, description="External user identifier")
    user_name: str | None = Field(default=None, description="User display name")
    metadata: dict | None = None


class ChatSessionResponse(BaseModel):
    """Response after creating a chat session."""
    session_id: uuid.UUID
    agent_id: uuid.UUID
    status: str
    welcome_message: str | None = None

    model_config = {"from_attributes": True}


class ChatMessageRequest(BaseModel):
    """Request to send a message to the agent."""
    content: str = Field(..., min_length=1, max_length=10000)
    metadata: dict | None = None


class ChatMessageResponse(BaseModel):
    """Agent's response to a user message."""
    message_id: uuid.UUID
    content: str
    state: str | None = None
    actions_executed: list[dict] = []
    status: str
    token_usage: dict | None = None


class ChatSessionDetail(BaseModel):
    """Full session with message history."""
    session_id: uuid.UUID
    agent_id: uuid.UUID
    status: str
    message_count: int
    messages: list[dict]


# --- Dependencies ---

async def validate_api_key(
    agent_id: uuid.UUID,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> Agent:
    """Validate the API key and return the agent."""
    # Find the agent
    agent = await db.get(Agent, agent_id)
    if not agent or agent.status != AgentStatus.PUBLISHED:
        raise HTTPException(status_code=404, detail="Agent not found or not published")

    # Validate API key — for MVP, compare directly (production should use bcrypt hash)
    stmt = select(ChatbotApiKey).where(
        ChatbotApiKey.agent_id == agent_id,
        ChatbotApiKey.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    api_keys = result.scalars().all()

    # Simple key validation — check if any key matches
    valid = False
    for key in api_keys:
        if key.key_hash == x_api_key:
            valid = True
            # Update last_used_at
            from datetime import datetime, timezone
            key.last_used_at = datetime.now(timezone.utc)
            break

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return agent


# --- Endpoints ---

@router.post(
    "/{agent_id}/sessions",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    agent_id: uuid.UUID,
    body: ChatSessionCreate | None = None,
    db: AsyncSession = Depends(get_db),
    agent: Agent = Depends(validate_api_key),
) -> ChatSessionResponse:
    """Create a new chat session with the agent."""
    from app.services.orchestrator import ConversationOrchestrator

    orchestrator = ConversationOrchestrator(db)
    conversation = await orchestrator.start_conversation(
        agent_id=agent_id,
        external_user_id=body.user_id if body else None,
        external_user_name=body.user_name if body else None,
    )

    return ChatSessionResponse(
        session_id=conversation.id,
        agent_id=agent_id,
        status=conversation.status.value,
        welcome_message=agent.welcome_message,
    )


@router.post(
    "/{agent_id}/sessions/{session_id}/messages",
    response_model=ChatMessageResponse,
)
async def send_message(
    agent_id: uuid.UUID,
    session_id: uuid.UUID,
    body: ChatMessageRequest,
    db: AsyncSession = Depends(get_db),
    agent: Agent = Depends(validate_api_key),
) -> ChatMessageResponse:
    """Send a message to the agent and get a response."""
    # Verify the session belongs to this agent
    conversation = await db.get(Conversation, session_id)
    if not conversation or conversation.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Session not found")
    if conversation.status != ConversationStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Session is no longer active")

    from app.services.orchestrator import ConversationOrchestrator

    orchestrator = ConversationOrchestrator(db)
    result = await orchestrator.process_message(
        conversation_id=session_id,
        user_message=body.content,
    )

    return ChatMessageResponse(
        message_id=uuid.uuid4(),  # The orchestrator stores the message; this is for the response
        content=result.message,
        state=result.state,
        actions_executed=result.actions_executed,
        status=result.status,
        token_usage=result.token_usage,
    )


@router.get(
    "/{agent_id}/sessions/{session_id}",
    response_model=ChatSessionDetail,
)
async def get_session(
    agent_id: uuid.UUID,
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    agent: Agent = Depends(validate_api_key),
) -> ChatSessionDetail:
    """Get session details with message history."""
    from sqlalchemy.orm import selectinload

    stmt = (
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == session_id, Conversation.agent_id == agent_id)
    )
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=404, detail="Session not found")

    return ChatSessionDetail(
        session_id=conversation.id,
        agent_id=conversation.agent_id,
        status=conversation.status.value,
        message_count=conversation.message_count,
        messages=[
            {
                "role": msg.role.value,
                "content": msg.content,
                "created_at": msg.created_at.isoformat(),
            }
            for msg in conversation.messages
        ],
    )


@router.delete(
    "/{agent_id}/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def end_session(
    agent_id: uuid.UUID,
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    agent: Agent = Depends(validate_api_key),
) -> None:
    """End a chat session."""
    conversation = await db.get(Conversation, session_id)
    if not conversation or conversation.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Session not found")

    from datetime import datetime, timezone
    conversation.status = ConversationStatus.COMPLETED
    conversation.ended_at = datetime.now(timezone.utc)
    await db.flush()
