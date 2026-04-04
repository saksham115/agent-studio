import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
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
    raise HTTPException(status_code=501, detail="Not implemented")


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
    raise HTTPException(status_code=501, detail="Not implemented")
