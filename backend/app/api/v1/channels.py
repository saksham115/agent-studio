import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, verify_agent_ownership
from app.config import settings
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
    """Create or update channel configuration for an agent."""
    if channel_type not in VALID_CHANNEL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid channel_type '{channel_type}'. Must be one of: {', '.join(sorted(VALID_CHANNEL_TYPES))}",
        )

    await verify_agent_ownership(agent_id, db, current_user)

    # For WhatsApp channels, auto-generate webhook URL and verify token
    webhook_url = config_in.webhook_url
    config_data = config_in.config

    if channel_type == "whatsapp":
        base = settings.PUBLIC_API_URL.rstrip("/")
        webhook_url = webhook_url or f"{base}/api/v1/webhooks/whatsapp/{agent_id}"
        if not config_data.get("verify_token"):
            config_data["verify_token"] = secrets.token_urlsafe(32)

        # Normalize camelCase keys from the frontend wizard to snake_case
        # so the webhook handler can find them
        key_map = {
            "metaAccessToken": "access_token",
            "metaPhoneNumberId": "phone_number_id",
            "metaBusinessAccountId": "business_account_id",
            "metaAppSecret": "app_secret",
            "metaVerifyToken": "meta_verify_token",
            "gupshupApiKey": "api_key",
            "gupshupAppName": "app_name",
        }
        for camel, snake in key_map.items():
            if camel in config_data and config_data[camel]:
                config_data[snake] = config_data[camel]

    # Check if channel already exists
    stmt = select(Channel).where(
        Channel.agent_id == agent_id,
        Channel.channel_type == channel_type,
    )
    result = await db.execute(stmt)
    channel = result.scalar_one_or_none()

    if channel:
        # Update existing channel
        channel.config = config_data
        if config_in.is_active is not None:
            channel.is_active = config_in.is_active
        if config_in.phone_number is not None:
            channel.phone_number = config_in.phone_number
        if webhook_url is not None:
            channel.webhook_url = webhook_url
    else:
        # Create new channel
        channel = Channel(
            agent_id=agent_id,
            channel_type=channel_type,
            config=config_data,
            is_active=config_in.is_active if config_in.is_active is not None else False,
            phone_number=config_in.phone_number,
            webhook_url=webhook_url,
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
    """List all channels configured for an agent."""
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
