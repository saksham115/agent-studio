import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, verify_agent_ownership
from app.models.agent import Agent, AgentStatus
from app.models.audit import ActionExecution, GuardrailTrigger, StateTransitionLog
from app.models.channel import Channel
from app.models.conversation import Conversation, ConversationStatus, Message, MessageRole
from app.models.state import State
from app.schemas.auth import CurrentUser
from app.schemas.conversation import AgentStatsResponse, DashboardStatsResponse

router = APIRouter()


@router.get(
    "/overview",
    response_model=DashboardStatsResponse,
)
async def get_dashboard_overview(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to look back"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> DashboardStatsResponse:
    """Get dashboard overview statistics for the organization.

    Returns aggregate metrics across all agents including total conversations,
    active conversations, message counts, average sentiment, and breakdowns
    by channel type and conversation status. Filtered by the specified time
    window (default 30 days).
    """
    org_id = current_user.org_id

    # -- total_agents & active_agents --
    total_agents = await db.scalar(
        select(func.count(Agent.id)).where(Agent.org_id == org_id)
    ) or 0

    active_agents = await db.scalar(
        select(func.count(Agent.id)).where(
            Agent.org_id == org_id,
            Agent.status == AgentStatus.PUBLISHED,
        )
    ) or 0

    # -- Conversation stats (join through Agent for org scoping) --
    conv_base = select(Conversation).join(Agent).where(Agent.org_id == org_id)

    total_conversations = await db.scalar(
        select(func.count()).select_from(conv_base.subquery())
    ) or 0

    active_conversations = await db.scalar(
        select(func.count()).select_from(
            conv_base.where(
                Conversation.status == ConversationStatus.ACTIVE
            ).subquery()
        )
    ) or 0

    # -- total_messages: join Message -> Conversation -> Agent --
    msg_stmt = (
        select(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .join(Agent, Conversation.agent_id == Agent.id)
        .where(Agent.org_id == org_id)
    )
    total_messages = await db.scalar(msg_stmt) or 0

    # -- avg_messages_per_conversation --
    avg_msgs = await db.scalar(
        select(func.avg(Conversation.message_count))
        .join(Agent, Conversation.agent_id == Agent.id)
        .where(Agent.org_id == org_id)
    )
    avg_messages_per_conversation = round(float(avg_msgs), 2) if avg_msgs is not None else 0.0

    # -- avg_sentiment_score --
    avg_sentiment = await db.scalar(
        select(func.avg(Conversation.sentiment_score))
        .join(Agent, Conversation.agent_id == Agent.id)
        .where(
            Agent.org_id == org_id,
            Conversation.sentiment_score.isnot(None),
        )
    )
    avg_sentiment_score = round(float(avg_sentiment), 4) if avg_sentiment is not None else None

    # -- conversations_by_status: group by status --
    status_rows = (
        await db.execute(
            select(Conversation.status, func.count())
            .join(Agent, Conversation.agent_id == Agent.id)
            .where(Agent.org_id == org_id)
            .group_by(Conversation.status)
        )
    ).all()
    conversations_by_status: dict[str, int] = {
        row[0].value: row[1] for row in status_rows
    }

    # -- conversations_by_channel: join Channel --
    channel_rows = (
        await db.execute(
            select(Channel.channel_type, func.count(Conversation.id))
            .join(Conversation, Conversation.channel_id == Channel.id)
            .join(Agent, Agent.id == Conversation.agent_id)
            .where(Agent.org_id == org_id)
            .group_by(Channel.channel_type)
        )
    ).all()
    conversations_by_channel: dict[str, int] = {
        (row[0].value if hasattr(row[0], "value") else str(row[0])): row[1]
        for row in channel_rows
    }

    # -- top_agents: top 5 by conversation count --
    top_rows = (
        await db.execute(
            select(
                Agent.id,
                Agent.name,
                func.count(Conversation.id).label("count"),
            )
            .outerjoin(Conversation, Conversation.agent_id == Agent.id)
            .where(Agent.org_id == org_id)
            .group_by(Agent.id, Agent.name)
            .order_by(func.count(Conversation.id).desc())
            .limit(5)
        )
    ).all()
    top_agents = [
        {
            "agent_id": str(r[0]),
            "name": r[1],
            "conversation_count": r[2],
        }
        for r in top_rows
    ]

    return DashboardStatsResponse(
        total_agents=total_agents,
        active_agents=active_agents,
        total_conversations=total_conversations,
        active_conversations=active_conversations,
        total_messages=total_messages,
        avg_messages_per_conversation=avg_messages_per_conversation,
        avg_sentiment_score=avg_sentiment_score,
        conversations_by_channel=conversations_by_channel,
        conversations_by_status=conversations_by_status,
        top_agents=top_agents,
    )


@router.get(
    "/{agent_id}/stats",
    response_model=AgentStatsResponse,
)
async def get_agent_stats(
    agent_id: uuid.UUID,
    days: int = Query(default=30, ge=1, le=365, description="Number of days to look back"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AgentStatsResponse:
    """Get detailed statistics for a specific agent.

    Returns per-agent metrics including conversation volume, average response
    latency, sentiment scores, guardrail trigger counts, action execution
    counts, daily conversation trends, and most visited states.
    """
    agent = await verify_agent_ownership(agent_id, db, current_user)

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # -- total_conversations --
    total_conversations = await db.scalar(
        select(func.count(Conversation.id)).where(
            Conversation.agent_id == agent_id
        )
    ) or 0

    # -- active_conversations --
    active_conversations = await db.scalar(
        select(func.count(Conversation.id)).where(
            Conversation.agent_id == agent_id,
            Conversation.status == ConversationStatus.ACTIVE,
        )
    ) or 0

    # -- total_messages --
    total_messages = await db.scalar(
        select(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.agent_id == agent_id)
    ) or 0

    # -- avg_messages_per_conversation --
    avg_msgs = await db.scalar(
        select(func.avg(Conversation.message_count)).where(
            Conversation.agent_id == agent_id
        )
    )
    avg_messages_per_conversation = round(float(avg_msgs), 2) if avg_msgs is not None else 0.0

    # -- avg_response_latency_ms: only for ASSISTANT messages --
    avg_latency = await db.scalar(
        select(func.avg(Message.latency_ms))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.agent_id == agent_id,
            Message.role == MessageRole.ASSISTANT,
            Message.latency_ms.isnot(None),
        )
    )
    avg_response_latency_ms = round(float(avg_latency), 2) if avg_latency is not None else None

    # -- avg_sentiment_score --
    avg_sentiment = await db.scalar(
        select(func.avg(Conversation.sentiment_score)).where(
            Conversation.agent_id == agent_id,
            Conversation.sentiment_score.isnot(None),
        )
    )
    avg_sentiment_score = round(float(avg_sentiment), 4) if avg_sentiment is not None else None

    # -- guardrail_triggers_count: join through Conversation --
    guardrail_triggers_count = await db.scalar(
        select(func.count(GuardrailTrigger.id))
        .join(Conversation, GuardrailTrigger.conversation_id == Conversation.id)
        .where(Conversation.agent_id == agent_id)
    ) or 0

    # -- action_executions_count: join through Conversation --
    action_executions_count = await db.scalar(
        select(func.count(ActionExecution.id))
        .join(Conversation, ActionExecution.conversation_id == Conversation.id)
        .where(Conversation.agent_id == agent_id)
    ) or 0

    # -- conversations_by_day: last N days grouped by day --
    day_rows = (
        await db.execute(
            select(
                func.date_trunc("day", Conversation.started_at).label("day"),
                func.count(Conversation.id),
            )
            .where(
                Conversation.agent_id == agent_id,
                Conversation.started_at >= cutoff,
            )
            .group_by(func.date_trunc("day", Conversation.started_at))
            .order_by(func.date_trunc("day", Conversation.started_at))
        )
    ).all()
    conversations_by_day = [
        {
            "date": r[0].strftime("%Y-%m-%d") if r[0] else "",
            "count": r[1],
        }
        for r in day_rows
    ]

    # -- conversations_by_status --
    status_rows = (
        await db.execute(
            select(Conversation.status, func.count())
            .where(Conversation.agent_id == agent_id)
            .group_by(Conversation.status)
        )
    ).all()
    conversations_by_status: dict[str, int] = {
        row[0].value: row[1] for row in status_rows
    }

    # -- top_states: from StateTransitionLog, group by to_state_id, top 5 --
    top_state_rows = (
        await db.execute(
            select(
                StateTransitionLog.to_state_id,
                State.name,
                func.count(StateTransitionLog.id).label("visit_count"),
            )
            .join(Conversation, StateTransitionLog.conversation_id == Conversation.id)
            .join(State, StateTransitionLog.to_state_id == State.id)
            .where(Conversation.agent_id == agent_id)
            .group_by(StateTransitionLog.to_state_id, State.name)
            .order_by(func.count(StateTransitionLog.id).desc())
            .limit(5)
        )
    ).all()
    top_states = [
        {
            "state_id": str(r[0]),
            "name": r[1],
            "visit_count": r[2],
        }
        for r in top_state_rows
    ]

    return AgentStatsResponse(
        agent_id=agent.id,
        agent_name=agent.name,
        total_conversations=total_conversations,
        active_conversations=active_conversations,
        total_messages=total_messages,
        avg_messages_per_conversation=avg_messages_per_conversation,
        avg_response_latency_ms=avg_response_latency_ms,
        avg_sentiment_score=avg_sentiment_score,
        guardrail_triggers_count=guardrail_triggers_count,
        action_executions_count=action_executions_count,
        conversations_by_day=conversations_by_day,
        conversations_by_status=conversations_by_status,
        top_states=top_states,
    )
