import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.agent import AgentStatus
from app.schemas.agent import (
    AgentCreate,
    AgentListResponse,
    AgentPublishResponse,
    AgentResponse,
    AgentUpdate,
)
from app.schemas.auth import CurrentUser
from app.services.agent_service import AgentService

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
    """Create a new AI sales agent in draft status."""
    service = AgentService(db)
    agent = await service.create_agent(
        org_id=uuid.UUID(str(current_user.org_id)),
        created_by=uuid.UUID(str(current_user.id)),
        name=agent_in.name,
        description=agent_in.description,
        system_prompt=agent_in.system_prompt,
        persona=agent_in.persona,
        languages=agent_in.languages,
        welcome_message=agent_in.welcome_message,
        fallback_message=agent_in.fallback_message,
        escalation_message=agent_in.escalation_message,
        max_turns=agent_in.max_turns,
        model_config_data=agent_in.model_config_data,
    )
    return AgentResponse.model_validate(agent)


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
    """List all agents in the current user's organization."""
    service = AgentService(db)

    parsed_status = None
    if status_filter:
        try:
            parsed_status = AgentStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status_filter}. Must be one of: {[s.value for s in AgentStatus]}",
            )

    agents, total = await service.list_agents(
        org_id=uuid.UUID(str(current_user.org_id)),
        page=page,
        page_size=page_size,
        status_filter=parsed_status,
        search=search,
    )

    return AgentListResponse(
        items=[AgentResponse.model_validate(a) for a in agents],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, math.ceil(total / page_size)),
    )


@router.get(
    "/{agent_id}",
    response_model=AgentResponse,
)
async def get_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AgentResponse:
    """Retrieve a specific agent by ID."""
    service = AgentService(db)
    agent = await service.get_agent_by_id(agent_id, uuid.UUID(str(current_user.org_id)))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentResponse.model_validate(agent)


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
    """Update an existing agent's configuration."""
    service = AgentService(db)
    agent = await service.get_agent_by_id(agent_id, uuid.UUID(str(current_user.org_id)))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = agent_in.model_dump(exclude_unset=True)
    if "model_config" in update_data:
        update_data["model_config_json"] = update_data.pop("model_config")

    agent = await service.update_agent(agent, **update_data)
    return AgentResponse.model_validate(agent)


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Soft-delete an agent by archiving it."""
    service = AgentService(db)
    agent = await service.get_agent_by_id(agent_id, uuid.UUID(str(current_user.org_id)))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await service.delete_agent(agent)


@router.post(
    "/{agent_id}/publish",
    response_model=AgentPublishResponse,
)
async def publish_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AgentPublishResponse:
    """Publish an agent, making it available for deployment."""
    service = AgentService(db)
    agent = await service.get_agent_by_id(agent_id, uuid.UUID(str(current_user.org_id)))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if not agent.system_prompt:
        raise HTTPException(
            status_code=400,
            detail="Agent must have a system prompt before publishing",
        )

    agent = await service.publish_agent(agent)
    return AgentPublishResponse(
        id=agent.id,
        status=agent.status.value,
        published_at=agent.published_at,
        published_version=agent.published_version,
    )
