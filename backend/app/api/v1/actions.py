import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.schemas.action import ActionCreate, ActionListResponse, ActionResponse, ActionUpdate
from app.schemas.auth import CurrentUser

router = APIRouter()


@router.post(
    "",
    response_model=ActionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_action(
    agent_id: uuid.UUID,
    action_in: ActionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ActionResponse:
    """Create a new action for an agent.

    Actions define operations the agent can perform during conversations,
    such as API calls, data lookups, handoffs to human agents, or custom
    tool invocations.
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get(
    "",
    response_model=ActionListResponse,
)
async def list_actions(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ActionListResponse:
    """List all actions configured for an agent.

    Returns action definitions including their type, configuration,
    input parameters, and active status.
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.put(
    "/{action_id}",
    response_model=ActionResponse,
)
async def update_action(
    agent_id: uuid.UUID,
    action_id: uuid.UUID,
    action_in: ActionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ActionResponse:
    """Update an existing action's configuration.

    Supports partial updates to the action's name, description, type,
    config, input parameters, and active status.
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete(
    "/{action_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_action(
    agent_id: uuid.UUID,
    action_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Delete an action from an agent.

    Removes the action definition. If the action is referenced by any
    state transitions, it will be deactivated instead of deleted.
    """
    raise HTTPException(status_code=501, detail="Not implemented")
