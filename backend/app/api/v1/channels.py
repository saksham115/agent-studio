import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, verify_agent_ownership
from app.models.channel import Channel
from app.schemas.auth import CurrentUser
from app.schemas.channel import ChannelConfigUpdate, ChannelListResponse, ChannelResponse

router = APIRouter()

VALID_CHANNEL_TYPES = {"voice", "whatsapp", "chatbot"}


@router.put(
    "/{channel_type}",
    response_model=ChannelResponse,
)
async def update_channel_config(
    agent_id: uuid.UUID,
    channel_type: str,
    config_in: ChannelConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ChannelResponse:
    """Create or update channel configuration for an agent.

    Configures a deployment channel (voice, whatsapp, or chatbot) for the agent.
    If the channel does not exist, it is created. If it exists, it is updated.

    For WhatsApp channels, this includes Gupshup provider configuration.
    For voice channels, this includes Exotel/Sarvam configuration.
    For chatbot channels, this generates an embeddable API key.
    """
    if channel_type not in VALID_CHANNEL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid channel_type '{channel_type}'. Must be one of: {', '.join(sorted(VALID_CHANNEL_TYPES))}",
        )

    await verify_agent_ownership(agent_id, db, current_user)

    # Check if channel already exists
    stmt = select(Channel).where(
        Channel.agent_id == agent_id,
        Channel.channel_type == channel_type,
    )
    result = await db.execute(stmt)
    channel = result.scalar_one_or_none()

    if channel:
        # Update existing channel
        channel.config = config_in.config
        if config_in.is_active is not None:
            channel.is_active = config_in.is_active
        if config_in.phone_number is not None:
            channel.phone_number = config_in.phone_number
        if config_in.webhook_url is not None:
            channel.webhook_url = config_in.webhook_url
    else:
        # Create new channel
        channel = Channel(
            agent_id=agent_id,
            channel_type=channel_type,
            config=config_in.config,
            is_active=config_in.is_active if config_in.is_active is not None else False,
            phone_number=config_in.phone_number,
            webhook_url=config_in.webhook_url,
        )
        db.add(channel)

    await db.flush()

    return ChannelResponse.model_validate(channel)


@router.get(
    "",
    response_model=ChannelListResponse,
)
async def list_channels(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ChannelListResponse:
    """List all channels configured for an agent.

    Returns channel configuration and status for voice, WhatsApp, and chatbot
    channels. Includes active/inactive status and provider details.
    """
    await verify_agent_ownership(agent_id, db, current_user)

    stmt = select(Channel).where(Channel.agent_id == agent_id).order_by(Channel.created_at)
    result = await db.execute(stmt)
    channels = result.scalars().all()

    count_stmt = select(func.count()).select_from(Channel).where(Channel.agent_id == agent_id)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    return ChannelListResponse(
        items=[ChannelResponse.model_validate(c) for c in channels],
        total=total,
    )
