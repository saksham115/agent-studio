"""Webhook endpoints for external service callbacks.

These endpoints are called by third-party services (Gupshup, Meta, Plivo)
and must be publicly accessible (no auth). They handle:

WhatsApp (Gupshup / Meta Cloud API):
- GET  /webhooks/whatsapp/{agent_id} — Webhook verification (hub.challenge)
- POST /webhooks/whatsapp/{agent_id} — Incoming message processing

Voice (Plivo + Sarvam AI):
- POST /webhooks/voice/incoming — Plivo answer_url; returns Plivo XML opening WS stream
- POST /webhooks/voice/status   — Plivo hangup_url; marks Conversation COMPLETED
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db
from app.config import settings
from app.models.channel import Channel, ChannelType, ChannelStatus
from app.models.channel import WhatsAppProvider as WhatsAppProviderModel
from app.models.conversation import Conversation
from app.services.channels.whatsapp.gupshup import GupshupAdapter
from app.services.channels.whatsapp.meta_cloud import MetaCloudAdapter
from app.services.channels.whatsapp.provider import WhatsAppProviderBase
from app.services.channels.whatsapp.handler import WhatsAppMessageHandler
from app.services.channels.voice.plivo import CallEvent, PlivoClient
from app.services.channels.voice.plivo_xml import (
    greeting_then_stream,
    say_response,
)
from app.services.channels.voice.handler import VoiceCallHandler

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory mapping of active call SIDs to conversation IDs.
# For production use a Redis-backed store; this is sufficient for the MVP.
_active_calls: dict[str, uuid.UUID] = {}


# --------------------------------------------------------------------------
# Webhook verification (GET)
# --------------------------------------------------------------------------


@router.get("/whatsapp/{agent_id}")
async def verify_whatsapp_webhook(
    agent_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    """Handle WhatsApp webhook verification (GET request).

    Gupshup / Meta Cloud API sends a GET request with query parameters:
    - ``hub.mode`` = "subscribe"
    - ``hub.challenge`` = a random string to echo back
    - ``hub.verify_token`` = the verify token configured in the dashboard

    We return the ``hub.challenge`` value as plain text to confirm the
    webhook URL.  If a verify token is configured on the channel, the
    incoming ``hub.verify_token`` must match.
    """
    params = request.query_params

    # -- Verify the token if configured ----------------------------------------
    channel, wa_provider = await _load_whatsapp_channel(db, agent_id)

    verify_token = ""
    if wa_provider:
        verify_token = wa_provider.webhook_verify_token or ""
    elif channel:
        verify_token = (channel.config or {}).get("verify_token", "")

    hub_verify_token = params.get("hub.verify_token", "")
    if verify_token and hub_verify_token != verify_token:
        logger.warning(
            "WhatsApp webhook verification failed for agent=%s — token mismatch",
            agent_id,
        )
        return PlainTextResponse(content="Forbidden", status_code=403)

    # -- Return the challenge --------------------------------------------------
    challenge = params.get("hub.challenge", "")

    if challenge:
        logger.info(
            "WhatsApp webhook verification for agent=%s — returning challenge",
            agent_id,
        )
        return PlainTextResponse(content=challenge, status_code=200)

    # Fallback: some Gupshup setups just ping the URL
    logger.info(
        "WhatsApp webhook verification ping for agent=%s (no challenge)", agent_id
    )
    return PlainTextResponse(content="OK", status_code=200)


# --------------------------------------------------------------------------
# Incoming message (POST)
# --------------------------------------------------------------------------


@router.post("/whatsapp/{agent_id}")
async def handle_whatsapp_webhook(
    agent_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Handle incoming WhatsApp messages from Gupshup or Meta Cloud API.

    Flow:
    1. Parse the raw webhook JSON payload.
    2. Look up the WhatsApp channel configuration for this agent.
    3. Create the appropriate adapter (Gupshup or Meta) from stored config.
    4. Parse the message via ``adapter.parse_webhook()``.
    5. Process via ``WhatsAppMessageHandler``.
    6. Send the agent's response back via ``adapter.send_text()``.
    7. Return 200 OK immediately (WhatsApp BSPs require a fast response).
    """
    # -- 1. Parse raw payload -------------------------------------------------
    try:
        payload = await request.json()
    except Exception:
        logger.warning("Failed to parse webhook JSON for agent=%s", agent_id)
        return JSONResponse(content={"status": "error", "detail": "Invalid JSON"}, status_code=400)

    print(f"[WEBHOOK] agent={agent_id} type={payload.get('object', '?')} entries={len(payload.get('entry', []))}", flush=True)
    logger.info("WhatsApp webhook payload for agent=%s: %s", agent_id, payload)

    # -- 2. Look up channel config --------------------------------------------
    channel, wa_provider = await _load_whatsapp_channel(db, agent_id)

    if channel is None:
        logger.warning(
            "No active WhatsApp channel found for agent=%s", agent_id
        )
        # Still return 200 so the BSP doesn't retry endlessly
        return JSONResponse(
            content={"status": "error", "detail": "WhatsApp channel not configured"},
            status_code=200,
        )

    # -- 3. Build adapter from stored config ----------------------------------
    adapter = _build_whatsapp_adapter(channel, wa_provider)

    # -- 4. Parse webhook payload ---------------------------------------------
    message = adapter.parse_webhook(payload)

    if message is None:
        # Not a user message (e.g. delivery receipt) — acknowledge silently
        logger.debug(
            "Non-message webhook event for agent=%s, acknowledging", agent_id
        )
        return JSONResponse(content={"status": "ok"}, status_code=200)

    logger.info(
        "Incoming WhatsApp message for agent=%s from=%s type=%s",
        agent_id,
        message.sender_phone,
        message.message_type,
    )

    # -- 5. Process through handler -------------------------------------------
    handler = WhatsAppMessageHandler(db)
    response_text = await handler.handle_incoming(agent_id, message, access_token=getattr(adapter, "access_token", ""))

    # -- 6. Send response back ------------------------------------------------
    send_result = await adapter.send_text(message.sender_phone, response_text)

    if not send_result.success:
        logger.error(
            "Failed to send WhatsApp reply to %s for agent=%s: %s",
            message.sender_phone,
            agent_id,
            send_result.error,
        )

    # -- 7. Return 200 OK to the BSP ------------------------------------------
    return JSONResponse(content={"status": "ok"}, status_code=200)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


async def _load_whatsapp_channel(
    db: AsyncSession, agent_id: uuid.UUID
) -> tuple[Channel | None, WhatsAppProviderModel | None]:
    """Load the active WhatsApp channel and its provider config for an agent."""
    # Find the WhatsApp channel for this agent
    stmt = (
        select(Channel)
        .where(
            Channel.agent_id == agent_id,
            Channel.channel_type == ChannelType.WHATSAPP,
            Channel.is_active.is_(True),
        )
    )
    result = await db.execute(stmt)
    channel = result.scalar_one_or_none()

    if channel is None:
        return None, None

    # Load the associated WhatsApp provider config
    provider_stmt = (
        select(WhatsAppProviderModel)
        .where(WhatsAppProviderModel.channel_id == channel.id)
    )
    provider_result = await db.execute(provider_stmt)
    wa_provider = provider_result.scalar_one_or_none()

    return channel, wa_provider


def _build_whatsapp_adapter(
    channel: Channel,
    wa_provider: WhatsAppProviderModel | None,
) -> WhatsAppProviderBase:
    """Construct the correct WhatsApp adapter based on the provider type.

    Inspects the provider name (from the ``WhatsAppProvider`` record or
    the channel ``config.provider`` field) and delegates to the
    provider-specific builder.
    """
    provider_type = ""
    if wa_provider:
        provider_type = wa_provider.provider_name or ""
    if not provider_type:
        provider_type = (channel.config or {}).get("provider", "gupshup")

    if provider_type == "meta_cloud":
        return _build_meta_adapter(channel, wa_provider)
    else:
        return _build_gupshup_adapter(channel, wa_provider)


def _build_gupshup_adapter(
    channel: Channel,
    wa_provider: WhatsAppProviderModel | None,
) -> GupshupAdapter:
    """Construct a GupshupAdapter from the channel and provider config.

    Credentials are resolved with the following priority:
    1. WhatsAppProvider record (``api_key_encrypted``, ``config``)
    2. Channel ``config`` JSONB field
    3. Global ``settings.GUPSHUP_API_KEY`` as a fallback
    """
    from app.config import settings

    # Resolve API key
    api_key = ""
    app_name = ""
    source_phone = channel.phone_number or ""
    webhook_secret: str | None = None

    if wa_provider:
        api_key = wa_provider.api_key_encrypted or ""
        webhook_secret = wa_provider.webhook_verify_token
        provider_config = wa_provider.config or {}
        app_name = provider_config.get("app_name", "")
        if not source_phone:
            source_phone = provider_config.get("source_phone", "")

    # Fall back to channel config
    channel_config = channel.config or {}
    if not api_key:
        api_key = channel_config.get("api_key", "")
    if not app_name:
        app_name = channel_config.get("app_name", "")
    if not source_phone:
        source_phone = channel_config.get("source_phone", channel_config.get("phone_number", ""))

    # Final fallback to global settings
    if not api_key:
        api_key = settings.GUPSHUP_API_KEY

    if not api_key:
        logger.error("No Gupshup API key configured for channel %s", channel.id)

    return GupshupAdapter(
        api_key=api_key,
        app_name=app_name,
        source_phone=source_phone,
        webhook_secret=webhook_secret,
    )


def _build_meta_adapter(
    channel: Channel,
    wa_provider: WhatsAppProviderModel | None,
) -> MetaCloudAdapter:
    """Construct a MetaCloudAdapter from the channel and provider config.

    Credentials are resolved with the following priority:
    1. WhatsAppProvider record (``api_key_encrypted``, ``phone_number_id``, ``config``)
    2. Channel ``config`` JSONB field
    """
    config = channel.config or {}
    access_token = ""
    phone_number_id = ""
    app_secret: str | None = None
    verify_token: str | None = None

    if wa_provider:
        access_token = wa_provider.api_key_encrypted or ""
        phone_number_id = wa_provider.phone_number_id or ""
        app_secret = (wa_provider.config or {}).get("app_secret")
        verify_token = wa_provider.webhook_verify_token

    if not access_token:
        access_token = config.get("access_token", "")
    if not phone_number_id:
        phone_number_id = config.get("phone_number_id", "")
    if not app_secret:
        app_secret = config.get("app_secret")
    if not verify_token:
        verify_token = config.get("verify_token")

    if not access_token:
        logger.error(
            "No Meta Cloud API access token configured for channel %s",
            channel.id,
        )

    return MetaCloudAdapter(
        access_token=access_token,
        phone_number_id=phone_number_id,
        app_secret=app_secret,
        verify_token=verify_token,
    )


# ==========================================================================
# Voice (Plivo + Sarvam AI) webhook endpoints
# ==========================================================================


def _verify_plivo_signature(
    request: Request,
    payload: dict,
    *,
    path: str,
) -> None:
    """Run Plivo V3 signature verification with log-only-mode toggle.

    PLIVO_VERIFY_SIGNATURES=false (default) logs failures but allows the request
    through — used during initial demo to confirm signatures actually work
    behind ngrok before flipping to fail-closed.

    Constructs the URL from PUBLIC_API_URL rather than ``request.url`` because
    ngrok / reverse-proxy rewriting changes what the FastAPI Request sees, and
    Plivo signed the public-facing URL.
    """
    plivo_client = PlivoClient()
    full_url = f"{settings.PUBLIC_API_URL.rstrip('/')}{path}"
    sig_ok = plivo_client.verify_signature(
        method="POST",
        url=full_url,
        params=payload,
        headers=request.headers,
    )
    if sig_ok:
        logger.info("Plivo signature OK on %s", path)
        return
    if settings.PLIVO_VERIFY_SIGNATURES:
        logger.warning("Invalid Plivo signature on %s (rejecting)", path)
        raise HTTPException(status_code=403, detail="Invalid Plivo signature")
    logger.warning("Plivo signature failed on %s (log-only mode; allowing)", path)


@router.post("/voice/incoming")
async def handle_voice_incoming(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Plivo answer_url. Returns Plivo XML to greet caller and open WS stream.

    Flow:
    1. Verify Plivo signature (log-only mode for first deploy).
    2. Parse webhook → CallEvent.
    3. Resolve agent by called DID (To field).
    4. Create Conversation + ephemeral Bolna agent.
    5. Return ``<Response><Speak>greeting</Speak><Stream>wss://...</Stream></Response>``.
    """
    form_data = await request.form()
    payload = dict(form_data)

    logger.info("Plivo /voice/incoming payload: %s", payload)
    _verify_plivo_signature(request, payload, path="/api/v1/webhooks/voice/incoming")

    plivo_client = PlivoClient()
    call_event = plivo_client.parse_webhook(payload)

    agent_id = await _resolve_agent_by_phone(db, call_event.to_number)
    if agent_id is None:
        logger.warning(
            "No agent for incoming call to %s (call_uuid=%s)",
            call_event.to_number, call_event.call_sid,
        )
        return Response(
            content=say_response("Sorry, this number is not in service."),
            media_type="application/xml",
        )

    channel = await _find_voice_channel(db, agent_id)
    channel_config = (channel.config or {}) if channel else {}
    language = channel_config.get("language", "en-IN")

    # Use the agent's actual welcome message in <Speak> rather than Bolna's
    # configured agent_welcome_message. Reason: Bolna's task_manager fires
    # __forced_first_message before its TTS WebSocket has connected, so the
    # welcome audio is silently dropped ("No welcome message audio to send,
    # marking welcome message as played"). Putting the greeting in our XML
    # makes it Plivo's TTS — reliable, plays before the WS even opens.
    from app.models.agent import Agent
    agent = (await db.execute(
        select(Agent).where(Agent.id == agent_id)
    )).scalar_one_or_none()
    greeting = (
        channel_config.get("greeting")
        or (agent.welcome_message if agent and agent.welcome_message else None)
        or "Hello! How can I help you today?"
    )

    # Create conversation + ephemeral Bolna agent.
    handler = VoiceCallHandler(db)
    try:
        conversation_id, _bolna_agent_id = await handler.handle_inbound_call(
            agent_id=agent_id,
            call_event=call_event,
        )
    except Exception:
        logger.exception("Failed to set up inbound voice call")
        return Response(
            content=say_response("Sorry, the agent is not available right now."),
            media_type="application/xml",
        )

    _active_calls[call_event.call_sid] = conversation_id

    # WebSocket URL Plivo will dial. conversation_id is appended as query param.
    ws_url = f"{settings.public_ws_url.rstrip('/')}/api/v1/voice/ws"
    return Response(
        content=greeting_then_stream(
            greeting_text=greeting,
            ws_url=ws_url,
            conversation_id=str(conversation_id),
            language=language,
        ),
        media_type="application/xml",
    )


@router.post("/voice/status")
async def handle_voice_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Plivo hangup_url + status callbacks.

    On terminal status (completed, failed, busy, no-answer, canceled), finalize
    the linked Conversation. Plivo also opens a transient 2nd WebSocket at
    hangup (Bolna issue #148) — voicebot_ws.py defends against duplicate
    connections; this handler just records the call-end.
    """
    form_data = await request.form()
    payload = dict(form_data)

    logger.info("Plivo /voice/status payload: %s", payload)
    _verify_plivo_signature(request, payload, path="/api/v1/webhooks/voice/status")

    plivo_client = PlivoClient()
    call_event = plivo_client.parse_webhook(payload)

    terminal_statuses = {"completed", "failed", "busy", "no-answer", "canceled"}
    if call_event.status in terminal_statuses:
        conversation_id = _active_calls.pop(call_event.call_sid, None)
        if conversation_id is None:
            conversation_id = await _find_conversation_by_call_sid(
                db, call_event.call_sid,
            )
        if conversation_id:
            handler = VoiceCallHandler(db)
            await handler.handle_call_end(conversation_id, call_event)
            logger.info(
                "Voice call finalized: call_uuid=%s, conversation_id=%s, status=%s",
                call_event.call_sid, conversation_id, call_event.status,
            )

    return {"status": "ok"}


# --------------------------------------------------------------------------
# Voice helpers
# --------------------------------------------------------------------------


async def _resolve_agent_by_phone(
    db: AsyncSession, phone_number: str,
) -> uuid.UUID | None:
    """Find the agent associated with a phone number via its voice channel.

    Resolution order:
    1. Exact match on Channel.phone_number.
    2. Digit-only comparison (handles "+918012345678" vs "918012345678" vs
       "08012345678" formatting differences).
    3. **MVP single-tenant fallback** — if there's exactly one active voice
       channel on the system, return it regardless of phone_number. This lets
       SIP Endpoint demos work without guessing what Plivo's ``To`` field
       contains (it's a SIP URI, not a phone number, and varies). For a
       multi-channel production deployment this fallback is intentionally
       conservative: only fires when the route is unambiguous.
    """
    stmt = select(Channel).where(
        Channel.channel_type == ChannelType.VOICE,
        Channel.is_active.is_(True),
        Channel.phone_number == phone_number,
    )
    channel = (await db.execute(stmt)).scalar_one_or_none()
    if channel:
        return channel.agent_id

    stripped = phone_number.lstrip("+").lstrip("0")
    stmt2 = select(Channel).where(
        Channel.channel_type == ChannelType.VOICE,
        Channel.is_active.is_(True),
    )
    channels = (await db.execute(stmt2)).scalars().all()
    for ch in channels:
        if ch.phone_number and ch.phone_number.lstrip("+").lstrip("0") == stripped:
            return ch.agent_id

    # MVP fallback — unambiguous single channel.
    if len(channels) == 1:
        logger.info(
            "Voice route fallback: no phone match for %r, but only one active "
            "voice channel exists — routing to agent_id=%s",
            phone_number, channels[0].agent_id,
        )
        return channels[0].agent_id
    return None


async def _find_voice_channel(
    db: AsyncSession, agent_id: uuid.UUID,
) -> Channel | None:
    """Return the agent's active voice Channel row (or None)."""
    stmt = select(Channel).where(
        Channel.agent_id == agent_id,
        Channel.channel_type == ChannelType.VOICE,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _find_conversation_by_call_sid(
    db: AsyncSession, call_sid: str,
) -> uuid.UUID | None:
    """Look up a conversation by Plivo's CallUUID stored in context.call_sid.

    The DB column key stays "call_sid" for compatibility with existing data;
    the value is whatever the telephony provider's unique-per-call ID is.
    """
    stmt = select(Conversation).where(
        Conversation.context["call_sid"].astext == call_sid,
    )
    conversation = (await db.execute(stmt)).scalar_one_or_none()
    return conversation.id if conversation else None
