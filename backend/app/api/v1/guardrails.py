import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.schemas.auth import CurrentUser
from app.schemas.guardrail import (
    GuardrailGenerateRequest,
    GuardrailListResponse,
    GuardrailResponse,
    GuardrailUpdate,
)

router = APIRouter()


@router.post(
    "/generate",
    response_model=GuardrailListResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_guardrails(
    agent_id: uuid.UUID,
    request: GuardrailGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> GuardrailListResponse:
    """Auto-generate guardrails for an agent using AI.

    Analyzes the agent's system prompt, persona, and knowledge base to
    generate recommended guardrails. Includes IRDAI compliance guardrails
    by default for insurance-related agents. Generated guardrails are saved
    as inactive drafts for the user to review and activate.
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.put(
    "",
    response_model=GuardrailListResponse,
)
async def update_guardrails(
    agent_id: uuid.UUID,
    guardrails: list[GuardrailUpdate],
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> GuardrailListResponse:
    """Bulk update guardrails for an agent.

    Accepts a list of guardrail updates. Each update is identified by its
    guardrail ID and can modify any subset of fields. Useful for batch
    activation/deactivation and priority reordering.
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get(
    "",
    response_model=GuardrailListResponse,
)
async def list_guardrails(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> GuardrailListResponse:
    """List all guardrails configured for an agent.

    Returns guardrail rules ordered by priority, including both manually
    created and auto-generated guardrails with their active status.
    """
    raise HTTPException(status_code=501, detail="Not implemented")
