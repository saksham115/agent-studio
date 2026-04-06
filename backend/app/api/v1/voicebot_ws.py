"""Exotel Voicebot WebSocket endpoint — bidirectional audio streaming.

Receives caller audio from Exotel via WebSocket, processes through
STT → LLM → TTS pipeline, and streams response audio back.

Protocol: Exotel sends JSON messages with events:
  - connected: WebSocket established
  - start: Call metadata (call_sid, from, to, media_format)
  - media: Base64-encoded raw PCM audio chunks
  - stop: Call ended

We send back:
  - media: Base64-encoded response audio chunks
  - mark: Notification when audio playback finishes
  - clear: Clear queued audio
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import struct
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory

logger = logging.getLogger(__name__)

router = APIRouter()

# Minimum audio buffer before triggering STT (1.5 seconds at 8kHz 16-bit mono = 24000 bytes)
MIN_AUDIO_BUFFER = 24000
# Silence threshold — if audio energy is below this, consider it silence
SILENCE_THRESHOLD = 200
# Consecutive silent chunks before triggering STT processing
SILENCE_CHUNKS_TRIGGER = 8  # ~800ms of silence at 100ms chunks


def _audio_energy(pcm_bytes: bytes) -> float:
    """Calculate RMS energy of 16-bit PCM audio."""
    if len(pcm_bytes) < 2:
        return 0.0
    samples = struct.unpack(f"<{len(pcm_bytes) // 2}h", pcm_bytes)
    if not samples:
        return 0.0
    return (sum(s * s for s in samples) / len(samples)) ** 0.5


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 8000) -> bytes:
    """Wrap raw PCM bytes in a WAV header."""
    import struct as st

    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = len(pcm_bytes)

    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(st.pack("<I", 36 + data_size))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(st.pack("<I", 16))  # chunk size
    buf.write(st.pack("<H", 1))  # PCM format
    buf.write(st.pack("<H", num_channels))
    buf.write(st.pack("<I", sample_rate))
    buf.write(st.pack("<I", byte_rate))
    buf.write(st.pack("<H", block_align))
    buf.write(st.pack("<H", bits_per_sample))
    buf.write(b"data")
    buf.write(st.pack("<I", data_size))
    buf.write(pcm_bytes)
    return buf.getvalue()


def _wav_to_pcm(wav_bytes: bytes) -> bytes:
    """Extract raw PCM data from WAV bytes (skip the 44-byte header)."""
    if wav_bytes[:4] == b"RIFF" and len(wav_bytes) > 44:
        return wav_bytes[44:]
    return wav_bytes


def _chunk_audio(pcm_bytes: bytes, chunk_size: int = 3200) -> list[bytes]:
    """Split PCM audio into chunks that are multiples of 320 bytes."""
    # Ensure chunk_size is a multiple of 320
    chunk_size = max(3200, (chunk_size // 320) * 320)
    chunks = []
    for i in range(0, len(pcm_bytes), chunk_size):
        chunk = pcm_bytes[i : i + chunk_size]
        # Pad last chunk to multiple of 320
        remainder = len(chunk) % 320
        if remainder:
            chunk += b"\x00" * (320 - remainder)
        chunks.append(chunk)
    return chunks


@router.websocket("/voice/{agent_id}/ws")
async def voicebot_websocket(websocket: WebSocket, agent_id: str):
    """Handle Exotel Voicebot bidirectional audio WebSocket."""
    await websocket.accept()

    import time as _time

    call_sid = ""
    stream_sid = ""
    sample_rate = 8000
    audio_buffer = bytearray()
    silence_count = 0
    conversation_id: uuid.UUID | None = None
    processing = False
    call_start_time = _time.time()

    logger.info("Voicebot WebSocket connected for agent=%s", agent_id)

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            event = msg.get("event")

            if event == "connected":
                logger.info("Voicebot stream connected")

            elif event == "start":
                start_data = msg.get("start", {})
                call_sid = start_data.get("call_sid", "")
                stream_sid = msg.get("stream_sid", "")
                from_number = start_data.get("from", "")
                media_format = start_data.get("media_format", {})
                sample_rate = int(media_format.get("sample_rate", 8000))

                logger.info(
                    "Voicebot call start: call_sid=%s, from=%s, stream_sid=%s, sample_rate=%d",
                    call_sid, from_number, stream_sid, sample_rate,
                )

                # Start conversation and send welcome audio in background
                # so the WebSocket loop keeps processing messages
                async def _greet():
                    nonlocal conversation_id
                    async with async_session_factory() as db:
                        conversation_id = await _start_conversation_and_greet(
                            websocket, db, agent_id, call_sid, from_number,
                            stream_sid, sample_rate,
                        )

                asyncio.create_task(_greet())

            elif event == "media":
                if processing:
                    continue

                payload = msg.get("media", {}).get("payload", "")
                if not payload:
                    continue

                pcm_chunk = base64.b64decode(payload)
                audio_buffer.extend(pcm_chunk)

                # Detect silence for end-of-speech
                energy = _audio_energy(pcm_chunk)
                if energy < SILENCE_THRESHOLD:
                    silence_count += 1
                else:
                    silence_count = 0

                # Process when we have enough audio and detect silence
                if len(audio_buffer) >= MIN_AUDIO_BUFFER and silence_count >= SILENCE_CHUNKS_TRIGGER:
                    processing = True
                    audio_data = bytes(audio_buffer)
                    audio_buffer.clear()
                    silence_count = 0

                    if conversation_id:
                        async def _process(data: bytes, conv_id: uuid.UUID):
                            nonlocal processing
                            try:
                                async with async_session_factory() as db:
                                    await _process_audio_turn(
                                        websocket, db, conv_id, agent_id,
                                        data, stream_sid, sample_rate,
                                    )
                            finally:
                                processing = False

                        asyncio.create_task(_process(audio_data, conversation_id))
                    else:
                        processing = False

            elif event == "stop":
                stop_reason = msg.get("stop", {}).get("reason", "unknown")
                logger.info("Voicebot call ended: call_sid=%s reason=%s", call_sid, stop_reason)
                # Finalize conversation
                if conversation_id:
                    async with async_session_factory() as db:
                        await _finalize_conversation(db, conversation_id)
                break

    except WebSocketDisconnect:
        logger.info("Voicebot WebSocket disconnected: call_sid=%s", call_sid)
        if conversation_id:
            async with async_session_factory() as db:
                await _finalize_conversation(db, conversation_id)
    except Exception:
        logger.exception("Voicebot WebSocket error: call_sid=%s", call_sid)


async def _start_conversation_and_greet(
    websocket: WebSocket,
    db: AsyncSession,
    agent_id: str,
    call_sid: str,
    from_number: str,
    stream_sid: str,
    sample_rate: int,
) -> uuid.UUID | None:
    """Start a conversation and stream the welcome audio."""
    from app.models.channel import Channel, ChannelType
    from app.services.channels.voice.handler import VoiceCallHandler
    from app.services.channels.voice.exotel import CallEvent

    # Get voice config
    language, speaker = await _get_voice_config(db, uuid.UUID(agent_id))

    call_event = CallEvent(
        call_sid=call_sid,
        from_number=from_number,
        to_number="",
        status="in-progress",
        direction="inbound",
    )

    handler = VoiceCallHandler(db)
    try:
        conversation_id, welcome_audio = await handler.handle_call_start(
            agent_id=uuid.UUID(agent_id),
            call_event=call_event,
            language=language,
            speaker=speaker,
        )
    except Exception:
        logger.exception("Failed to start voice conversation")
        return None

    # Stream welcome audio back
    if welcome_audio:
        pcm_data = _wav_to_pcm(welcome_audio)
        await _stream_audio(websocket, pcm_data, stream_sid)

    await db.commit()
    return conversation_id


async def _process_audio_turn(
    websocket: WebSocket,
    db: AsyncSession,
    conversation_id: uuid.UUID,
    agent_id: str,
    audio_data: bytes,
    stream_sid: str,
    sample_rate: int,
) -> None:
    """Process one turn: STT → Orchestrator → TTS → stream back."""
    from app.services.channels.voice.handler import VoiceCallHandler

    language, speaker = await _get_voice_config(db, uuid.UUID(agent_id))

    # Wrap PCM in WAV for STT
    wav_data = _pcm_to_wav(audio_data, sample_rate)

    handler = VoiceCallHandler(db)
    response_audio = await handler.handle_audio_input(
        conversation_id=conversation_id,
        audio_data=wav_data,
        language=language,
        speaker=speaker,
    )

    if response_audio:
        # Clear any queued audio first
        await websocket.send_text(json.dumps({
            "event": "clear",
            "stream_sid": stream_sid,
        }))

        pcm_data = _wav_to_pcm(response_audio)
        await _stream_audio(websocket, pcm_data, stream_sid)

    await db.commit()


async def _stream_audio(
    websocket: WebSocket,
    pcm_data: bytes,
    stream_sid: str,
) -> None:
    """Stream PCM audio back to Exotel in properly sized chunks."""
    chunks = _chunk_audio(pcm_data)
    for i, chunk in enumerate(chunks):
        msg = {
            "event": "media",
            "stream_sid": stream_sid,
            "media": {
                "chunk": i + 1,
                "payload": base64.b64encode(chunk).decode("ascii"),
            },
        }
        await websocket.send_text(json.dumps(msg))

    # Send mark to know when audio finishes playing
    await websocket.send_text(json.dumps({
        "event": "mark",
        "stream_sid": stream_sid,
        "mark": {"name": "response_end"},
    }))


async def _finalize_conversation(db: AsyncSession, conversation_id: uuid.UUID) -> None:
    """Mark the conversation as completed."""
    from app.models.conversation import Conversation, ConversationStatus
    from sqlalchemy import select

    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()
    if conversation and conversation.status == ConversationStatus.ACTIVE:
        conversation.status = ConversationStatus.COMPLETED
        from datetime import datetime, timezone
        conversation.ended_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info("Voice conversation finalized: %s", conversation_id)


async def _get_voice_config(db: AsyncSession, agent_id: uuid.UUID) -> tuple[str, str]:
    """Read language and speaker from the voice channel config."""
    from app.models.channel import Channel, ChannelType
    from sqlalchemy import select

    stmt = select(Channel).where(
        Channel.agent_id == agent_id,
        Channel.channel_type == ChannelType.VOICE,
    )
    result = await db.execute(stmt)
    channel = result.scalar_one_or_none()

    if channel and channel.config:
        language = channel.config.get("language") or channel.config.get("workingHoursStart") or "hi-IN"
        speaker = channel.config.get("speaker") or channel.config.get("ttsVoice") or "anushka"
        return language, speaker

    return "hi-IN", "anushka"
