"""Exotel Voicebot WebSocket endpoint — powered by Bolna.

Receives Exotel WebSocket connection, extracts call metadata, creates
a conversation via our orchestrator, then hands off to Bolna's
AssistantManager for the full STT → LLM → TTS pipeline.

Bolna handles: streaming STT (Sarvam), turn detection (VAD),
barge-in/interruption, streaming TTS (Sarvam), audio formatting.

Our OrchestratorLLM adapter bridges Bolna's LLM interface to our
ConversationOrchestrator (tools, state machine, guardrails, KB).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.services.channels.voice.bolna_config import build_bolna_agent_config
from app.services.channels.voice.ws_proxy import ReplayableWebSocket

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/voice/{agent_id}/ws")
async def voicebot_websocket(websocket: WebSocket, agent_id: str):
    """Handle Exotel Voicebot WebSocket via Bolna."""
    await websocket.accept()
    logger.info("Voicebot WebSocket connected for agent=%s", agent_id)

    # Collect initial events to extract call metadata
    buffered_messages: list[str] = []
    call_sid = ""
    from_number = ""
    conversation_id: uuid.UUID | None = None

    try:
        # Read initial events (connected, start) to get call metadata
        for _ in range(5):  # Max 5 attempts to find the start event
            raw = await websocket.receive_text()
            buffered_messages.append(raw)
            msg = json.loads(raw)
            event = msg.get("event")

            if event == "connected":
                logger.info("Voicebot stream connected")

            elif event == "start":
                start_data = msg.get("start", {})
                call_sid = start_data.get("call_sid", "")
                from_number = start_data.get("from", "")
                logger.info(
                    "Voicebot call start: call_sid=%s, from=%s",
                    call_sid, from_number,
                )
                break

        if not call_sid:
            logger.error("Never received start event, closing")
            await websocket.close()
            return

        # Create conversation and build Bolna config
        async with async_session_factory() as db:
            conversation_id, agent_config = await _setup_conversation(
                db, agent_id, call_sid, from_number,
            )
            await db.commit()

        logger.info(
            "Bolna session starting: conversation_id=%s, agent=%s",
            conversation_id, agent_id,
        )

        # Wrap WebSocket to replay buffered messages for Bolna
        proxy_ws = ReplayableWebSocket(websocket, buffered_messages)

        # Run Bolna AssistantManager
        from bolna.agent_manager.assistant_manager import AssistantManager

        assistant = AssistantManager(
            agent_config=agent_config,
            ws=proxy_ws,
            assistant_id=agent_id,
            # These kwargs flow through to OrchestratorLLM.__init__
            conversation_id=conversation_id,
            db_session_factory=async_session_factory,
        )

        async for task_id, task_output in assistant.run(local=True):
            logger.info("Bolna task %d completed: %s", task_id, str(task_output)[:200])

    except WebSocketDisconnect:
        logger.info("Voicebot WebSocket disconnected: call_sid=%s", call_sid)
    except Exception:
        logger.exception("Voicebot WebSocket error: call_sid=%s", call_sid)
    finally:
        # Finalize conversation
        if conversation_id:
            try:
                async with async_session_factory() as db:
                    await _finalize_conversation(db, conversation_id)
            except Exception:
                logger.exception("Failed to finalize conversation %s", conversation_id)

        logger.info("Voicebot session ended: call_sid=%s, conversation_id=%s", call_sid, conversation_id)


async def _setup_conversation(
    db: AsyncSession,
    agent_id: str,
    call_sid: str,
    from_number: str,
) -> tuple[uuid.UUID, dict]:
    """Create a conversation and build the Bolna config."""
    from app.services.orchestrator import ConversationOrchestrator

    agent_uuid = uuid.UUID(agent_id)

    # Start conversation via orchestrator (stores welcome message in DB)
    orchestrator = ConversationOrchestrator(db)
    orch_response = await orchestrator.start_conversation(agent_uuid)
    conversation_id = orch_response.conversation_id

    # Store voice-specific metadata
    from app.models.conversation import Conversation
    from app.models.channel import Channel, ChannelType

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

    # Link to voice channel
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

    # Build Bolna agent config
    agent_config = await build_bolna_agent_config(db, agent_uuid)

    return conversation_id, agent_config


async def _finalize_conversation(db: AsyncSession, conversation_id: uuid.UUID) -> None:
    """Mark the conversation as completed."""
    from app.models.conversation import Conversation, ConversationStatus

    conversation = (await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )).scalar_one_or_none()

    if conversation and conversation.status.value == "active":
        conversation.status = ConversationStatus.COMPLETED
        conversation.ended_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info("Voice conversation finalized: %s", conversation_id)
