"""Voice call handler — orchestrates the STT -> LLM -> TTS pipeline.

This module ties together Sarvam AI speech services and the conversation
orchestrator to process a voice call turn-by-turn over HTTP.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel, ChannelType
from app.models.conversation import Conversation, ConversationStatus
from app.services.channels.voice.exotel import CallEvent
from app.services.channels.voice.sarvam import SarvamSTT, SarvamTTS
from app.services.orchestrator import ConversationOrchestrator

logger = logging.getLogger(__name__)


class VoiceCallHandler:
    """Handles the end-to-end voice call flow.

    For each call turn the pipeline is:

    1. Receive raw audio from the telephony layer.
    2. Transcribe via Sarvam STT (Saarika v2).
    3. Feed the transcript to the conversation orchestrator.
    4. Synthesize the orchestrator's text reply via Sarvam TTS (Bulbul v2).
    5. Return the audio bytes to the telephony layer.

    Usage::

        handler = VoiceCallHandler(db)
        conv_id, welcome_audio = await handler.handle_call_start(agent_id, call_event)
        response_audio = await handler.handle_audio_input(conv_id, raw_audio)
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.stt = SarvamSTT()
        self.tts = SarvamTTS()
        self.orchestrator = ConversationOrchestrator(db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def handle_call_start(
        self,
        agent_id: uuid.UUID,
        call_event: CallEvent,
        language: str = "hi-IN",
        speaker: str = "meera",
    ) -> tuple[uuid.UUID, bytes]:
        """Handle a new incoming voice call.

        Creates a conversation via the orchestrator, synthesizes the welcome
        message into audio, and returns both the conversation ID and the
        welcome audio bytes.

        Args:
            agent_id: The agent that should handle this call.
            call_event: Parsed Exotel call-event with caller metadata.
            language: Language code for TTS synthesis.
            speaker: Sarvam TTS voice ID.

        Returns:
            A tuple of ``(conversation_id, welcome_audio_bytes)``.
        """
        logger.info(
            "Voice call start: agent_id=%s, call_sid=%s, from=%s",
            agent_id,
            call_event.call_sid,
            call_event.from_number,
        )

        # Start a new conversation through the orchestrator
        orch_response = await self.orchestrator.start_conversation(agent_id)
        conversation_id = orch_response.conversation_id

        # Store voice-specific metadata on the conversation
        conversation = await self._load_conversation(conversation_id)
        if conversation:
            conversation.external_user_phone = call_event.from_number
            conversation.language = language
            conversation.context = {
                **(conversation.context or {}),
                "channel": "voice",
                "call_sid": call_event.call_sid,
                "direction": call_event.direction,
            }

            # Link to voice channel if configured
            channel = await self._find_voice_channel(agent_id)
            if channel:
                conversation.channel_id = channel.id

            await self.db.flush()

        # Synthesize the welcome message into audio
        welcome_text = orch_response.message
        try:
            welcome_audio = await self.tts.synthesize(
                text=welcome_text,
                language=language,
                speaker=speaker,
            )
        except Exception:
            logger.error(
                "TTS synthesis failed for welcome message, returning empty audio",
                exc_info=True,
            )
            welcome_audio = b""

        logger.info(
            "Voice call started: conversation_id=%s, welcome_audio_size=%d bytes",
            conversation_id,
            len(welcome_audio),
        )
        return conversation_id, welcome_audio

    async def handle_audio_input(
        self,
        conversation_id: uuid.UUID,
        audio_data: bytes,
        language: str = "hi-IN",
        speaker: str = "meera",
    ) -> bytes:
        """Process a single audio turn: STT -> orchestrator -> TTS.

        Args:
            conversation_id: Active conversation to continue.
            audio_data: Raw audio bytes from the caller.
            language: Language code for STT/TTS.
            speaker: Sarvam TTS voice ID.

        Returns:
            Synthesized response audio bytes.
        """
        logger.info(
            "Voice audio input: conversation_id=%s, audio_size=%d bytes",
            conversation_id,
            len(audio_data),
        )

        # --- Step 1: Transcribe audio via Sarvam STT -------------------------
        try:
            transcription = await self.stt.transcribe(
                audio_data=audio_data,
                language=language,
            )
        except Exception:
            logger.error("STT transcription failed", exc_info=True)
            # Return a spoken error message to the caller
            error_audio = await self._synthesize_error(
                "Sorry, I could not understand the audio. Please try again.",
                language=language,
                speaker=speaker,
            )
            return error_audio

        user_text = transcription.text.strip()
        if not user_text:
            logger.warning("STT returned empty transcript for conversation %s", conversation_id)
            empty_audio = await self._synthesize_error(
                "I didn't catch that. Could you please repeat?",
                language=language,
                speaker=speaker,
            )
            return empty_audio

        logger.info(
            "STT transcript: conversation_id=%s, text=%r",
            conversation_id,
            user_text[:200],
        )

        # --- Step 2: Process via orchestrator ---------------------------------
        # Prepend a voice-channel hint so the LLM keeps responses concise.
        voice_hint = (
            "[VOICE CALL: Keep your response under 2-3 short sentences. "
            "Be conversational and concise — the user is listening, not reading.]\n\n"
        )
        try:
            orch_response = await self.orchestrator.process_message(
                conversation_id=conversation_id,
                user_message=voice_hint + user_text,
            )
        except Exception:
            logger.error(
                "Orchestrator failed for conversation %s",
                conversation_id,
                exc_info=True,
            )
            error_audio = await self._synthesize_error(
                "Sorry, something went wrong. Please try again.",
                language=language,
                speaker=speaker,
            )
            return error_audio

        response_text = orch_response.message
        logger.info(
            "Orchestrator response: conversation_id=%s, text=%r",
            conversation_id,
            response_text[:200],
        )

        # --- Step 3: Synthesize response via Sarvam TTS -----------------------
        try:
            response_audio = await self.tts.synthesize(
                text=response_text,
                language=language,
                speaker=speaker,
            )
        except Exception:
            logger.error(
                "TTS synthesis failed for conversation %s",
                conversation_id,
                exc_info=True,
            )
            response_audio = b""

        logger.info(
            "Voice response: conversation_id=%s, audio_size=%d bytes",
            conversation_id,
            len(response_audio),
        )
        return response_audio

    async def handle_call_end(
        self,
        conversation_id: uuid.UUID,
        call_event: CallEvent,
    ) -> None:
        """Handle call completion — update conversation status and metadata.

        Args:
            conversation_id: The conversation tied to this call.
            call_event: Final Exotel call event with duration/recording info.
        """
        logger.info(
            "Voice call end: conversation_id=%s, call_sid=%s, duration=%s",
            conversation_id,
            call_event.call_sid,
            call_event.duration,
        )

        conversation = await self._load_conversation(conversation_id)
        if not conversation:
            logger.warning("Conversation %s not found during call_end", conversation_id)
            return

        # Mark conversation as completed
        conversation.status = ConversationStatus.COMPLETED
        conversation.ended_at = datetime.now(timezone.utc)

        # Store call metadata
        conversation.context = {
            **(conversation.context or {}),
            "call_duration": call_event.duration,
            "call_status": call_event.status,
            "recording_url": call_event.recording_url,
            "call_ended_at": datetime.now(timezone.utc).isoformat(),
        }

        await self.db.flush()
        logger.info("Voice call ended: conversation_id=%s", conversation_id)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _load_conversation(self, conversation_id: uuid.UUID) -> Conversation | None:
        """Load a conversation by ID."""
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _find_voice_channel(self, agent_id: uuid.UUID) -> Channel | None:
        """Find the voice channel configured for an agent."""
        stmt = select(Channel).where(
            Channel.agent_id == agent_id,
            Channel.channel_type == ChannelType.VOICE,
            Channel.is_active.is_(True),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _synthesize_error(
        self,
        message: str,
        language: str = "hi-IN",
        speaker: str = "meera",
    ) -> bytes:
        """Attempt to synthesize an error message; return empty bytes on failure."""
        try:
            return await self.tts.synthesize(text=message, language=language, speaker=speaker)
        except Exception:
            logger.error("Failed to synthesize error message via TTS", exc_info=True)
            return b""
