import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.schemas.auth import CurrentUser
from app.schemas.state import StateDiagramResponse, StateDiagramSave

router = APIRouter()


@router.put(
    "",
    response_model=StateDiagramResponse,
)
async def save_state_diagram(
    agent_id: uuid.UUID,
    diagram: StateDiagramSave,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> StateDiagramResponse:
    """Save the complete state diagram for an agent.

    Replaces the entire state diagram (nodes and edges) with the provided
    data. This is an idempotent operation -- the frontend sends the full
    diagram each time, and the backend reconciles by deleting removed
    nodes/edges and upserting the rest.

    Validates that exactly one initial state exists and that all transition
    references point to valid state IDs.
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get(
    "",
    response_model=StateDiagramResponse,
)
async def get_state_diagram(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> StateDiagramResponse:
    """Load the complete state diagram for an agent.

    Returns all states (nodes) and transitions (edges) that make up the
    agent's conversation flow diagram. Used by the visual state editor
    in the frontend.
    """
    raise HTTPException(status_code=501, detail="Not implemented")
