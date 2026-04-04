import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.schemas.auth import CurrentUser
from app.schemas.conversation import ConversationDetailResponse, ConversationListResponse

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
    raise HTTPException(status_code=501, detail="Not implemented")


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
    raise HTTPException(status_code=501, detail="Not implemented")


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
    raise HTTPException(status_code=501, detail="Not implemented")
