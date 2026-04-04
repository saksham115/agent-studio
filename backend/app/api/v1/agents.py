import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.schemas.agent import (
    AgentCreate,
    AgentListResponse,
    AgentPublishResponse,
    AgentResponse,
    AgentUpdate,
)
from app.schemas.auth import CurrentUser

router = APIRouter()


@router.post(
    "",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent(
    agent_in: AgentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AgentResponse:
    """Create a new AI sales agent.

    Creates a draft agent under the current user's organization with the
    provided name, description, system prompt, persona, and other configuration.
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get(
    "",
    response_model=AgentListResponse,
)
async def list_agents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AgentListResponse:
    """List all agents in the current user's organization.

    Supports pagination, filtering by status, and text search on name/description.
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get(
    "/{agent_id}",
    response_model=AgentResponse,
)
async def get_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AgentResponse:
    """Retrieve a specific agent by ID.

    Returns full agent details including configuration, status, and metadata.
    Only agents belonging to the current user's organization are accessible.
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.put(
    "/{agent_id}",
    response_model=AgentResponse,
)
async def update_agent(
    agent_id: uuid.UUID,
    agent_in: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AgentResponse:
    """Update an existing agent's configuration.

    Only draft agents can be fully updated. Published agents require creating
    a new version. Partial updates are supported.
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Delete an agent and all associated resources.

    Soft-deletes the agent by archiving it. Published agents cannot be deleted
    while they have active channels; channels must be deactivated first.
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post(
    "/{agent_id}/publish",
    response_model=AgentPublishResponse,
)
async def publish_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AgentPublishResponse:
    """Publish an agent, making it available for deployment on channels.

    Validates that the agent has a system prompt, at least one state, and
    required configuration before transitioning its status to published.
    Increments the published version number.
    """
    raise HTTPException(status_code=501, detail="Not implemented")
