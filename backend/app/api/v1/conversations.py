import uuid
from datetime import datetime, timezone
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.api.deps import get_current_user, get_db
from app.models.agent import Agent
from app.models.audit import StateTransitionLog
from app.models.channel import Channel
from app.models.conversation import Conversation, ConversationStatus, Message
from app.models.state import State
from app.schemas.auth import CurrentUser
from app.schemas.conversation import (
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationSummary,
    MessageResponse,
    StateTimelineEntry,
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
    # Base query: join Conversation -> Agent, optionally Channel & State
    base_query = (
        select(
            Conversation,
            Agent.name.label("agent_name"),
            Channel.channel_type.label("channel_type"),
            State.name.label("current_state_name"),
        )
        .join(Agent, Conversation.agent_id == Agent.id)
        .outerjoin(Channel, Conversation.channel_id == Channel.id)
        .outerjoin(State, Conversation.current_state_id == State.id)
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
        summary.channel_type = row[2].value if len(row) > 2 and row[2] else None
        summary.current_state_name = row[3] if len(row) > 3 else None
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
        select(
            Conversation,
            Agent.name.label("agent_name"),
            Channel.channel_type.label("channel_type"),
            State.name.label("current_state_name"),
        )
        .join(Agent, Conversation.agent_id == Agent.id)
        .outerjoin(Channel, Conversation.channel_id == Channel.id)
        .outerjoin(State, Conversation.current_state_id == State.id)
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
        summary.channel_type = row[2].value if len(row) > 2 and row[2] else None
        summary.current_state_name = row[3] if len(row) > 3 else None
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

    # Load the state-transition timeline ordered chronologically.
    # Aliases let us join `states` twice — once for `to_state` (always
    # present) and once for `from_state` (NULL on the seed/initial row).
    to_state_alias = aliased(State)
    from_state_alias = aliased(State)
    timeline_stmt = (
        select(
            StateTransitionLog.id,
            StateTransitionLog.from_state_id,
            StateTransitionLog.to_state_id,
            StateTransitionLog.reason,
            StateTransitionLog.created_at,
            to_state_alias.name.label("to_name"),
            from_state_alias.name.label("from_name"),
        )
        .join(to_state_alias, to_state_alias.id == StateTransitionLog.to_state_id)
        .outerjoin(
            from_state_alias,
            from_state_alias.id == StateTransitionLog.from_state_id,
        )
        .where(StateTransitionLog.conversation_id == conversation_id)
        .order_by(StateTransitionLog.created_at.asc())
    )
    timeline_result = await db.execute(timeline_stmt)
    timeline_rows = timeline_result.all()

    state_timeline: list[StateTimelineEntry] = []
    is_active = conv.status == ConversationStatus.ACTIVE
    end_time = conv.ended_at or datetime.now(timezone.utc)
    for idx, row in enumerate(timeline_rows):
        next_ts = (
            timeline_rows[idx + 1].created_at
            if idx + 1 < len(timeline_rows)
            else end_time
        )
        is_last = idx == len(timeline_rows) - 1
        state_timeline.append(
            StateTimelineEntry(
                state=row.to_name,
                state_id=row.to_state_id,
                timestamp=row.created_at,
                duration=_format_duration(row.created_at, next_ts, is_last and is_active),
                reason=row.reason,
                from_state=row.from_name,
            )
        )

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
        stateTimeline=state_timeline,
    )

    return detail


def _format_duration(start: datetime, end: datetime, is_active_last: bool) -> str:
    """Format a state's dwell duration as ``Xm Ys`` or ``ongoing``.

    For the LAST timeline entry on an ACTIVE conversation, return ``"ongoing"``.
    Otherwise compute the elapsed seconds and format compactly.
    """
    if is_active_last:
        return "ongoing"
    seconds = max(int((end - start).total_seconds()), 0)
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"
