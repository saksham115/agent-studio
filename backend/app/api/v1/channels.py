import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.schemas.auth import CurrentUser
from app.schemas.channel import ChannelConfigUpdate, ChannelListResponse, ChannelResponse

router = APIRouter()


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
    raise HTTPException(status_code=501, detail="Not implemented")


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
    raise HTTPException(status_code=501, detail="Not implemented")
