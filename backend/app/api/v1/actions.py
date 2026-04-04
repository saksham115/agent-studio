import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, verify_agent_ownership
from app.models.action import Action
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
    await verify_agent_ownership(agent_id, db, current_user)

    action = Action(agent_id=agent_id, **action_in.model_dump())
    db.add(action)
    await db.flush()

    return ActionResponse.model_validate(action)


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
    await verify_agent_ownership(agent_id, db, current_user)

    # Fetch actions ordered by creation date
    stmt = select(Action).where(Action.agent_id == agent_id).order_by(Action.created_at)
    result = await db.execute(stmt)
    actions = result.scalars().all()

    # Count total
    count_stmt = select(func.count()).select_from(Action).where(Action.agent_id == agent_id)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    return ActionListResponse(
        items=[ActionResponse.model_validate(a) for a in actions],
        total=total,
    )


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
    await verify_agent_ownership(agent_id, db, current_user)

    # Fetch the action
    stmt = select(Action).where(Action.id == action_id)
    result = await db.execute(stmt)
    action = result.scalar_one_or_none()

    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    if action.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Action not found for this agent")

    # Apply partial update
    update_data = action_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(action, field, value)

    await db.flush()

    return ActionResponse.model_validate(action)


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
    await verify_agent_ownership(agent_id, db, current_user)

    # Fetch the action
    stmt = select(Action).where(Action.id == action_id)
    result = await db.execute(stmt)
    action = result.scalar_one_or_none()

    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    if action.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Action not found for this agent")

    await db.delete(action)
