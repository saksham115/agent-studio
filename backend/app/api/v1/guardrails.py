import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, verify_agent_ownership
from app.models.guardrail import Guardrail
from app.schemas.auth import CurrentUser
from app.schemas.guardrail import (
    GuardrailGenerateRequest,
    GuardrailListResponse,
    GuardrailResponse,
    GuardrailUpdate,
)
from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

router = APIRouter()


async def _fetch_all_guardrails(
    agent_id: uuid.UUID, db: AsyncSession
) -> GuardrailListResponse:
    """Helper to fetch all guardrails for an agent and return as response."""
    stmt = (
        select(Guardrail)
        .where(Guardrail.agent_id == agent_id)
        .order_by(Guardrail.priority.desc())
    )
    result = await db.execute(stmt)
    guardrails = result.scalars().all()

    count_stmt = select(func.count()).select_from(Guardrail).where(Guardrail.agent_id == agent_id)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    return GuardrailListResponse(
        items=[GuardrailResponse.model_validate(g) for g in guardrails],
        total=total,
    )


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
    agent = await verify_agent_ownership(agent_id, db, current_user)

    system_prompt = agent.system_prompt or ""
    persona = agent.persona or ""

    # Build the prompt for guardrail generation
    type_filter = ""
    if request.guardrail_types:
        type_filter = f"\nFocus on these guardrail types: {', '.join(request.guardrail_types)}"

    compliance_note = ""
    if request.include_compliance:
        compliance_note = "\nInclude IRDAI compliance guardrails if the agent is insurance-related."

    generation_prompt = f"""Analyze the following agent configuration and generate appropriate guardrails.

## Agent System Prompt
{system_prompt}

## Agent Persona
{persona}
{type_filter}{compliance_note}

Generate a JSON array of guardrail objects. Each object must have these fields:
- "name": string (short descriptive name)
- "description": string (what this guardrail does)
- "guardrail_type": one of "input", "output", "topic", "compliance", "pii", "custom"
- "rule": string (the actual rule/instruction)
- "action": one of "block", "warn", "redirect", "log"
- "priority": integer (0-100, higher = more important)

Return ONLY the JSON array, no other text or markdown formatting."""

    try:
        client = LLMClient()
        response = await client.chat(
            system_prompt="You are a guardrail generation assistant. You analyze agent configurations and generate appropriate safety guardrails. Always respond with valid JSON only.",
            messages=[{"role": "user", "content": generation_prompt}],
            max_tokens=4096,
            temperature=0.3,
        )

        # Parse the JSON response
        content = response.content.strip()
        # Handle possible markdown code blocks
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        guardrail_data = json.loads(content)

        if not isinstance(guardrail_data, list):
            raise ValueError("Expected a JSON array of guardrails")

        # Create guardrail records
        for g_data in guardrail_data:
            guardrail = Guardrail(
                agent_id=agent_id,
                name=g_data.get("name", "Unnamed Guardrail"),
                description=g_data.get("description"),
                guardrail_type=g_data.get("guardrail_type", "custom"),
                rule=g_data.get("rule", ""),
                action=g_data.get("action", "block"),
                priority=g_data.get("priority", 0),
                is_active=False,
                is_auto_generated=True,
            )
            db.add(guardrail)

        await db.flush()

    except json.JSONDecodeError:
        logger.error("Failed to parse LLM response as JSON for guardrail generation")
        raise HTTPException(
            status_code=500,
            detail="Failed to parse generated guardrails. Please try again.",
        )
    except Exception as exc:
        logger.exception("Failed to generate guardrails for agent %s", agent_id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate guardrails: {str(exc)}",
        )

    return await _fetch_all_guardrails(agent_id, db)


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
    await verify_agent_ownership(agent_id, db, current_user)

    for update in guardrails:
        stmt = select(Guardrail).where(Guardrail.id == update.id)
        result = await db.execute(stmt)
        guardrail = result.scalar_one_or_none()

        if not guardrail:
            raise HTTPException(
                status_code=404,
                detail=f"Guardrail {update.id} not found",
            )
        if guardrail.agent_id != agent_id:
            raise HTTPException(
                status_code=404,
                detail=f"Guardrail {update.id} not found for this agent",
            )

        update_data = update.model_dump(exclude_unset=True, exclude={"id"})
        for field, value in update_data.items():
            setattr(guardrail, field, value)

    await db.flush()

    return await _fetch_all_guardrails(agent_id, db)


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
    await verify_agent_ownership(agent_id, db, current_user)

    return await _fetch_all_guardrails(agent_id, db)
