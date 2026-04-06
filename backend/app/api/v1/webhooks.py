"""Webhook endpoints for external service callbacks.

These endpoints are called by third-party services (Gupshup, Meta, Exotel)
and must be publicly accessible (no auth). They handle:

WhatsApp (Gupshup / Meta Cloud API):
- GET  /webhooks/whatsapp/{agent_id} — Webhook verification (hub.challenge)
- POST /webhooks/whatsapp/{agent_id} — Incoming message processing

Voice (Exotel + Sarvam AI):
- POST /webhooks/voice/incoming — Handle incoming voice call
- POST /webhooks/voice/status   — Handle call status callbacks
- POST /webhooks/voice/audio    — Handle audio input during a call
"""

from __future__ import annotations

import base64
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db
from app.models.channel import Channel, ChannelType, ChannelStatus
from app.models.channel import WhatsAppProvider as WhatsAppProviderModel
from app.models.conversation import Conversation
from app.services.channels.whatsapp.gupshup import GupshupAdapter
from app.services.channels.whatsapp.meta_cloud import MetaCloudAdapter
from app.services.channels.whatsapp.provider import WhatsAppProviderBase
from app.services.channels.whatsapp.handler import WhatsAppMessageHandler
from app.services.channels.voice.exotel import CallEvent, ExotelClient
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

    logger.debug("WhatsApp webhook payload for agent=%s: %s", agent_id, payload)

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
    response_text = await handler.handle_incoming(agent_id, message)

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
        access_token = config.get("access_token") or config.get("metaAccessToken") or ""
    if not phone_number_id:
        phone_number_id = config.get("phone_number_id") or config.get("metaPhoneNumberId") or ""
    if not app_secret:
        app_secret = config.get("app_secret") or config.get("metaAppSecret")
    if not verify_token:
        verify_token = config.get("verify_token") or config.get("metaVerifyToken")

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
# Voice (Exotel + Sarvam AI) webhook endpoints
# ==========================================================================


@router.post("/voice/incoming")
async def handle_voice_incoming(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Handle an incoming voice call from Exotel.

    Exotel POSTs form data when a call arrives at the configured webhook
    URL.  This endpoint:

    1. Parses the Exotel payload into a :class:`CallEvent`.
    2. Looks up the agent associated with the called phone number.
    3. Starts a new conversation via :class:`VoiceCallHandler`.
    4. Returns an XML (ExoML) response that plays the welcome TTS audio.
    """
    form_data = await request.form()
    payload = dict(form_data)

    logger.info("Voice incoming webhook received: %s", payload)

    exotel_client = ExotelClient()
    call_event = exotel_client.parse_webhook(payload)

    # Find the agent by the called phone number (To field)
    agent_id = await _resolve_agent_by_phone(db, call_event.to_number)
    if agent_id is None:
        logger.warning(
            "No agent found for phone number %s (call_sid=%s)",
            call_event.to_number,
            call_event.call_sid,
        )
        return _exoml_say("Sorry, this number is not configured. Goodbye.")

    # Determine language from channel config or default to hi-IN
    language, speaker = await _get_voice_config(db, agent_id)

    # Start the voice conversation
    handler = VoiceCallHandler(db)
    try:
        conversation_id, welcome_audio = await handler.handle_call_start(
            agent_id=agent_id,
            call_event=call_event,
            language=language,
            speaker=speaker,
        )
    except ValueError as exc:
        logger.error("Failed to start voice conversation: %s", exc)
        return _exoml_say("Sorry, the agent is not available right now. Goodbye.")

    # Track this call
    _active_calls[call_event.call_sid] = conversation_id

    # Return ExoML that plays the welcome audio
    if welcome_audio:
        audio_b64 = base64.b64encode(welcome_audio).decode("ascii")
        return _exoml_play_and_gather(
            audio_base64=audio_b64,
            action_url="/api/v1/webhooks/voice/audio",
            call_sid=call_event.call_sid,
        )
    else:
        return _exoml_say("Hello! How can I help you today?")


@router.post("/voice/status")
async def handle_voice_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Handle Exotel call status callbacks.

    Called when the call status changes (ringing, in-progress, completed,
    failed, etc.).  When the call ends we update the conversation status.
    """
    form_data = await request.form()
    payload = dict(form_data)

    logger.info("Voice status webhook received: %s", payload)

    exotel_client = ExotelClient()
    call_event = exotel_client.parse_webhook(payload)

    # If the call has ended, finalize the conversation
    terminal_statuses = {"completed", "failed", "busy", "no-answer", "canceled"}
    if call_event.status in terminal_statuses:
        conversation_id = _active_calls.pop(call_event.call_sid, None)
        if conversation_id:
            handler = VoiceCallHandler(db)
            await handler.handle_call_end(conversation_id, call_event)
            logger.info(
                "Voice call finalized: call_sid=%s, conversation_id=%s, status=%s",
                call_event.call_sid,
                conversation_id,
                call_event.status,
            )

    return {"status": "ok"}


@router.post("/voice/audio")
async def handle_voice_audio(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Handle audio input during a voice call.

    This endpoint receives the caller's recorded audio (from an ExoML
    ``<Record>`` or ``<Gather>`` verb, or posted directly by the
    telephony integration), processes it through the STT -> LLM -> TTS
    pipeline, and returns the response audio.

    Expected request body:
    - ``multipart/form-data`` with ``audio`` file and ``CallSid`` field, OR
    - ``application/json`` with ``audio_base64`` and ``call_sid`` fields.
    """
    content_type = request.headers.get("content-type", "")

    audio_data: bytes | None = None
    call_sid: str = ""

    if "multipart/form-data" in content_type:
        form_data = await request.form()
        call_sid = str(form_data.get("CallSid", form_data.get("call_sid", "")))

        # Try to get audio from uploaded file
        audio_file = form_data.get("audio") or form_data.get("RecordingFile")
        if audio_file and hasattr(audio_file, "read"):
            audio_data = await audio_file.read()

        # Fallback: check for recording URL in Exotel callback
        recording_url = form_data.get("RecordingUrl", form_data.get("recording_url"))
        if not audio_data and recording_url:
            audio_data = await _download_recording(str(recording_url))
    else:
        # JSON body
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid request body")

        call_sid = body.get("call_sid", "")
        audio_b64 = body.get("audio_base64", "")
        if audio_b64:
            audio_data = base64.b64decode(audio_b64)

    if not call_sid:
        raise HTTPException(status_code=400, detail="Missing call_sid")

    if not audio_data:
        raise HTTPException(status_code=400, detail="No audio data received")

    # Look up conversation for this call
    conversation_id = _active_calls.get(call_sid)
    if not conversation_id:
        # Try to find by call_sid in conversation context
        conversation_id = await _find_conversation_by_call_sid(db, call_sid)
        if conversation_id:
            _active_calls[call_sid] = conversation_id

    if not conversation_id:
        logger.warning("No active conversation for call_sid=%s", call_sid)
        return _exoml_say("Sorry, I could not find your conversation. Goodbye.")

    # Retrieve language/speaker settings from the conversation
    language, speaker = await _get_voice_config_for_conversation(db, conversation_id)

    # Process through the voice pipeline
    handler = VoiceCallHandler(db)
    response_audio = await handler.handle_audio_input(
        conversation_id=conversation_id,
        audio_data=audio_data,
        language=language,
        speaker=speaker,
    )

    if response_audio:
        audio_b64 = base64.b64encode(response_audio).decode("ascii")
        return _exoml_play_and_gather(
            audio_base64=audio_b64,
            action_url="/api/v1/webhooks/voice/audio",
            call_sid=call_sid,
        )
    else:
        return _exoml_say("Sorry, I couldn't generate a response. Please try again.")


# --------------------------------------------------------------------------
# Voice helpers
# --------------------------------------------------------------------------


async def _resolve_agent_by_phone(db: AsyncSession, phone_number: str) -> uuid.UUID | None:
    """Find the agent associated with a phone number via its voice channel."""
    stmt = select(Channel).where(
        Channel.channel_type == ChannelType.VOICE,
        Channel.is_active.is_(True),
        Channel.phone_number == phone_number,
    )
    result = await db.execute(stmt)
    channel = result.scalar_one_or_none()

    if channel:
        return channel.agent_id

    # Retry without country-code prefix (Exotel sometimes strips it)
    stripped = phone_number.lstrip("+").lstrip("0")
    stmt2 = select(Channel).where(
        Channel.channel_type == ChannelType.VOICE,
        Channel.is_active.is_(True),
    )
    result2 = await db.execute(stmt2)
    channels = result2.scalars().all()
    for ch in channels:
        if ch.phone_number and ch.phone_number.lstrip("+").lstrip("0") == stripped:
            return ch.agent_id

    return None


async def _get_voice_config(db: AsyncSession, agent_id: uuid.UUID) -> tuple[str, str]:
    """Read language and speaker from the voice channel config, with defaults."""
    stmt = select(Channel).where(
        Channel.agent_id == agent_id,
        Channel.channel_type == ChannelType.VOICE,
    )
    result = await db.execute(stmt)
    channel = result.scalar_one_or_none()

    if channel and channel.config:
        language = channel.config.get("language", "hi-IN")
        speaker = channel.config.get("speaker", "meera")
        return language, speaker

    return "hi-IN", "meera"


async def _get_voice_config_for_conversation(
    db: AsyncSession,
    conversation_id: uuid.UUID,
) -> tuple[str, str]:
    """Resolve voice config from the conversation's agent channel."""
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()

    if conversation:
        lang = conversation.language or "hi-IN"
        _, speaker = await _get_voice_config(db, conversation.agent_id)
        return lang, speaker

    return "hi-IN", "meera"


async def _find_conversation_by_call_sid(
    db: AsyncSession,
    call_sid: str,
) -> uuid.UUID | None:
    """Look up a conversation by the Exotel call_sid stored in context."""
    stmt = select(Conversation).where(
        Conversation.context["call_sid"].astext == call_sid,
    )
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()
    return conversation.id if conversation else None


async def _download_recording(url: str) -> bytes | None:
    """Download audio from an Exotel recording URL."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
    except Exception:
        logger.error("Failed to download recording from %s", url, exc_info=True)
        return None


def _exoml_say(message: str) -> Response:
    """Return a minimal ExoML response that speaks a message and hangs up."""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        f"  <Say>{message}</Say>\n"
        "  <Hangup/>\n"
        "</Response>"
    )
    return Response(content=xml, media_type="application/xml")


def _exoml_play_and_gather(
    audio_base64: str,
    action_url: str,
    call_sid: str,
) -> Response:
    """Return ExoML that plays audio and gathers the next recording.

    The response plays the synthesized audio, then records the caller's
    next utterance and POSTs it to the ``action_url`` for processing.
    """
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        f'  <Play type="audio/wav">{audio_base64}</Play>\n'
        f'  <Record action="{action_url}?call_sid={call_sid}" '
        f'maxLength="30" timeout="5" finishOnKey="#"/>\n'
        "</Response>"
    )
    return Response(content=xml, media_type="application/xml")
