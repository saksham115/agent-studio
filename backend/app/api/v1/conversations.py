import uuid
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.models.agent import Agent
from app.models.conversation import Conversation, Message
from app.schemas.auth import CurrentUser
from app.schemas.conversation import (
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationSummary,
    MessageResponse,
)

router = APIRouter()


@router.get(
    "",
    response_model=ConversationListResponse,
)
async def list_conversations(
    agent_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ConversationListResponse:
    """List conversations across all agents or filtered by agent.

    Returns a paginated list of conversations with summary information.
    Can be filtered by agent ID, conversation status, and date range.
    Only conversations from the current user's organization are returned.
    """
    # Base query: join Conversation -> Agent and scope by org_id
    base_query = (
        select(Conversation, Agent.name.label("agent_name"))
        .join(Agent, Conversation.agent_id == Agent.id)
        .where(Agent.org_id == uuid.UUID(str(current_user.org_id)))
    )

    # Optional filters
    if agent_id is not None:
        base_query = base_query.where(Conversation.agent_id == agent_id)
    if status_filter is not None:
        base_query = base_query.where(Conversation.status == status_filter)

    # Count total matching records
    count_query = select(func.count()).select_from(base_query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar_one()

    total_pages = ceil(total / page_size) if total > 0 else 1

    # Paginated data query
    data_query = (
        base_query
        .order_by(Conversation.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(data_query)
    rows = result.all()

    items = []
    for row in rows:
        conv = row[0]
        agent_name = row[1]
        summary = ConversationSummary.model_validate(conv)
        summary.agent_name = agent_name
        items.append(summary)

    return ConversationListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/search",
    response_model=ConversationListResponse,
)
async def search_conversations(
    q: str = Query(..., min_length=1, description="Search query string"),
    agent_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ConversationListResponse:
    """Search conversations by message content or user information.

    Performs full-text search across conversation messages, external user
    names, and phone numbers. Results are ranked by relevance.
    """
    org_id = uuid.UUID(str(current_user.org_id))

    # Build base query: join Conversation -> Agent -> Messages, filter by content
    base_query = (
        select(Conversation.id)
        .join(Agent, Conversation.agent_id == Agent.id)
        .join(Message, Message.conversation_id == Conversation.id)
        .where(Agent.org_id == org_id)
        .where(Message.content.ilike(f"%{q}%"))
        .distinct()
    )

    if agent_id is not None:
        base_query = base_query.where(Conversation.agent_id == agent_id)

    # Count total matching conversations
    count_query = select(func.count()).select_from(base_query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar_one()

    total_pages = ceil(total / page_size) if total > 0 else 1

    # Get paginated conversation IDs
    ids_query = base_query.offset((page - 1) * page_size).limit(page_size)
    ids_result = await db.execute(ids_query)
    conv_ids = [row[0] for row in ids_result.all()]

    if not conv_ids:
        return ConversationListResponse(
            items=[],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    # Fetch full conversation data for the matched IDs
    data_query = (
        select(Conversation, Agent.name.label("agent_name"))
        .join(Agent, Conversation.agent_id == Agent.id)
        .where(Conversation.id.in_(conv_ids))
        .order_by(Conversation.created_at.desc())
    )
    result = await db.execute(data_query)
    rows = result.all()

    items = []
    for row in rows:
        conv = row[0]
        agent_name = row[1]
        summary = ConversationSummary.model_validate(conv)
        summary.agent_name = agent_name
        items.append(summary)

    return ConversationListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetailResponse,
)
async def get_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ConversationDetailResponse:
    """Retrieve a specific conversation with all its messages.

    Returns full conversation details including metadata, current state,
    context, and the complete message history ordered chronologically.
    """
    org_id = uuid.UUID(str(current_user.org_id))

    # Load conversation with messages eager-loaded, join Agent to verify org
    stmt = (
        select(Conversation, Agent.name.label("agent_name"))
        .join(Agent, Conversation.agent_id == Agent.id)
        .where(Conversation.id == conversation_id)
        .where(Agent.org_id == org_id)
        .options(selectinload(Conversation.messages))
    )
    result = await db.execute(stmt)
    row = result.unique().first()

    if not row:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conv = row[0]
    agent_name = row[1]

    detail = ConversationDetailResponse(
        id=conv.id,
        agent_id=conv.agent_id,
        agent_name=agent_name,
        channel_id=conv.channel_id,
        external_user_id=conv.external_user_id,
        external_user_phone=conv.external_user_phone,
        external_user_name=conv.external_user_name,
        status=conv.status.value if hasattr(conv.status, "value") else conv.status,
        current_state_id=conv.current_state_id,
        context=conv.context,
        message_count=conv.message_count,
        language=conv.language,
        sentiment_score=conv.sentiment_score,
        started_at=conv.started_at,
        ended_at=conv.ended_at,
        messages=[MessageResponse.model_validate(m) for m in conv.messages],
    )

    return detail
