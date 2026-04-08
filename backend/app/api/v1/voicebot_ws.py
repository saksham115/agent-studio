"""Voice call initiation endpoint for the Bolna sidecar architecture.

When a voice channel is activated or an inbound call arrives, this module
creates an ephemeral Bolna agent and returns the WebSocket URL that Exotel
should connect to. Bolna handles the full audio pipeline (STT/TTS/VAD),
and calls back to our voice_completions endpoint for LLM responses.

The WebSocket route is kept for backward compatibility — Exotel's ExoML
app still points here, and we redirect to Bolna.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory
from app.services.channels.voice.bolna_config import build_bolna_agent_config
from app.services.channels.voice.bolna_service import BolnaService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/voice/{agent_id}/ws")
async def voicebot_websocket(websocket: WebSocket, agent_id: str):
    """Handle Exotel WebSocket by proxying to Bolna sidecar.

    Flow:
    1. Accept connection, read start event for call metadata
    2. Create conversation + ephemeral Bolna agent
    3. Proxy all WebSocket messages between Exotel and Bolna
    """
    await websocket.accept()
    logger.info("Voicebot WebSocket connected for agent=%s", agent_id)

    call_sid = ""
    from_number = ""
    conversation_id: uuid.UUID | None = None
    bolna_agent_id: str | None = None

    try:
        # Read initial events to get call metadata
        buffered: list[str] = []
        for _ in range(5):
            raw = await websocket.receive_text()
            buffered.append(raw)
            msg = json.loads(raw)

            if msg.get("event") == "start":
                start_data = msg.get("start", {})
                call_sid = start_data.get("call_sid", "")
                from_number = start_data.get("from", "")
                logger.info("Call start: call_sid=%s, from=%s", call_sid, from_number)
                break

        if not call_sid:
            logger.error("No start event received, closing")
            await websocket.close()
            return

        # Create conversation and Bolna agent
        async with async_session_factory() as db:
            conversation_id, bolna_agent_id = await _setup_call(
                db, agent_id, call_sid, from_number,
            )
            await db.commit()

        logger.info(
            "Call setup: conversation=%s, bolna_agent=%s",
            conversation_id, bolna_agent_id,
        )

        # Proxy WebSocket to Bolna
        import websockets

        bolna_ws_url = f"{settings.BOLNA_WS_URL}/chat/v1/{bolna_agent_id}"
        logger.info("Connecting to Bolna: %s", bolna_ws_url)

        async with websockets.connect(bolna_ws_url) as bolna_ws:
            import asyncio

            # Replay buffered messages to Bolna
            for msg in buffered:
                await bolna_ws.send(msg)

            # Bidirectional proxy
            async def exotel_to_bolna():
                try:
                    while True:
                        data = await websocket.receive_text()
                        await bolna_ws.send(data)
                except WebSocketDisconnect:
                    await bolna_ws.close()
                except Exception:
                    pass

            async def bolna_to_exotel():
                try:
                    async for data in bolna_ws:
                        await websocket.send_text(data)
                except Exception:
                    pass

            await asyncio.gather(
                exotel_to_bolna(),
                bolna_to_exotel(),
            )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: call_sid=%s", call_sid)
    except Exception:
        logger.exception("Voicebot error: call_sid=%s", call_sid)
    finally:
        # Finalize
        if conversation_id:
            try:
                async with async_session_factory() as db:
                    await _finalize_call(db, conversation_id)
            except Exception:
                logger.exception("Failed to finalize conversation %s", conversation_id)

        if bolna_agent_id:
            try:
                bolna = BolnaService()
                await bolna.delete_agent(bolna_agent_id)
            except Exception:
                logger.exception("Failed to delete Bolna agent %s", bolna_agent_id)

        logger.info("Call ended: call_sid=%s, conversation=%s", call_sid, conversation_id)


async def _setup_call(
    db: AsyncSession,
    agent_id: str,
    call_sid: str,
    from_number: str,
) -> tuple[uuid.UUID, str]:
    """Create conversation + ephemeral Bolna agent for this call."""
    from app.models.conversation import Conversation
    from app.models.channel import Channel, ChannelType
    from app.services.orchestrator import ConversationOrchestrator

    agent_uuid = uuid.UUID(agent_id)

    # Create conversation
    orchestrator = ConversationOrchestrator(db)
    orch_response = await orchestrator.start_conversation(agent_uuid)
    conversation_id = orch_response.conversation_id

    # Store call metadata
    conversation = (await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )).scalar_one()
    conversation.external_user_phone = from_number
    conversation.context = {
        **(conversation.context or {}),
        "channel": "voice",
        "call_sid": call_sid,
        "direction": "inbound",
    }

    channel = (await db.execute(
        select(Channel).where(
            Channel.agent_id == agent_uuid,
            Channel.channel_type == ChannelType.VOICE,
            Channel.is_active.is_(True),
        )
    )).scalar_one_or_none()
    if channel:
        conversation.channel_id = channel.id

    await db.flush()

    # Build Bolna config and create ephemeral agent
    agent_config = await build_bolna_agent_config(db, agent_uuid)
    bolna = BolnaService()
    bolna_agent_id = await bolna.create_call_agent(
        agent_config=agent_config,
        conversation_id=conversation_id,
        system_prompt="",  # Orchestrator handles prompts
    )

    return conversation_id, bolna_agent_id


async def _finalize_call(db: AsyncSession, conversation_id: uuid.UUID) -> None:
    """Mark conversation as completed."""
    from app.models.conversation import Conversation, ConversationStatus

    conversation = (await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )).scalar_one_or_none()

    if conversation and conversation.status.value == "active":
        conversation.status = ConversationStatus.COMPLETED
        conversation.ended_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info("Voice conversation finalized: %s", conversation_id)
