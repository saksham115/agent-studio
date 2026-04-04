import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, verify_agent_ownership
from app.models.state import State, Transition
from app.schemas.auth import CurrentUser
from app.schemas.state import (
    StateDiagramResponse,
    StateDiagramSave,
    StateResponse,
    TransitionResponse,
)

router = APIRouter()


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
    await verify_agent_ownership(agent_id, db, current_user)

    states_result = await db.execute(
        select(State).where(State.agent_id == agent_id)
    )
    states = states_result.scalars().all()

    transitions_result = await db.execute(
        select(Transition).where(Transition.agent_id == agent_id)
    )
    transitions = transitions_result.scalars().all()

    return StateDiagramResponse(
        nodes=[StateResponse.model_validate(s) for s in states],
        edges=[TransitionResponse.model_validate(t) for t in transitions],
    )


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
    await verify_agent_ownership(agent_id, db, current_user)

    # --- Validate ---
    if diagram.nodes:
        initial_count = sum(1 for node in diagram.nodes if node.is_initial)
        if initial_count != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Exactly one initial state is required, but found {initial_count}.",
            )

    node_ids = {node.id for node in diagram.nodes}
    for edge in diagram.edges:
        if edge.from_state_id not in node_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Edge references unknown from_state_id: {edge.from_state_id}",
            )
        if edge.to_state_id not in node_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Edge references unknown to_state_id: {edge.to_state_id}",
            )

    # --- Delete existing ---
    await db.execute(delete(Transition).where(Transition.agent_id == agent_id))
    await db.execute(delete(State).where(State.agent_id == agent_id))
    await db.flush()

    # --- Create new states ---
    id_map: dict[str, uuid.UUID] = {}
    new_states: list[State] = []
    for node in diagram.nodes:
        new_uuid = uuid.uuid4()
        id_map[node.id] = new_uuid
        new_states.append(
            State(
                id=new_uuid,
                agent_id=agent_id,
                name=node.name,
                description=node.description,
                instructions=node.instructions,
                is_initial=node.is_initial,
                is_terminal=node.is_terminal,
                position_x=node.position_x,
                position_y=node.position_y,
                metadata_json=node.metadata,
            )
        )
    db.add_all(new_states)
    await db.flush()

    # --- Create new transitions ---
    new_transitions: list[Transition] = []
    for edge in diagram.edges:
        new_transitions.append(
            Transition(
                id=uuid.uuid4(),
                agent_id=agent_id,
                from_state_id=id_map[edge.from_state_id],
                to_state_id=id_map[edge.to_state_id],
                condition=edge.condition,
                description=edge.description,
                priority=edge.priority,
                metadata_json=edge.metadata,
            )
        )
    db.add_all(new_transitions)
    await db.flush()

    # --- Re-query and return ---
    states_result = await db.execute(
        select(State).where(State.agent_id == agent_id)
    )
    states = states_result.scalars().all()

    transitions_result = await db.execute(
        select(Transition).where(Transition.agent_id == agent_id)
    )
    transitions = transitions_result.scalars().all()

    return StateDiagramResponse(
        nodes=[StateResponse.model_validate(s) for s in states],
        edges=[TransitionResponse.model_validate(t) for t in transitions],
    )
