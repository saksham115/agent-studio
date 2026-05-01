"""Voice call handler — bridges webhook events to orchestrator + Bolna sidecar.

For Plivo's WebSocket-streaming flow we only need two operations:

1. ``handle_inbound_call`` — when Plivo's answer_url fires, create a Conversation
   and an ephemeral Bolna agent. Returns both IDs so the webhook can put the
   ``bolna_agent_id`` in the WS URL and the ``conversation_id`` in
   ``Conversation.context``.
2. ``handle_call_end`` — when Plivo's hangup_url fires, mark the Conversation
   COMPLETED and stash call metadata.

The previous Exotel turn-based flow (``handle_call_start`` / ``handle_audio_input``
with Sarvam HTTP STT/TTS) is gone. Bolna handles STT/LLM/TTS over the WebSocket
directly; our backend is just the proxy + setup layer.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel, ChannelType
from app.models.conversation import Conversation, ConversationStatus
from app.services.channels.voice.bolna_config import build_bolna_agent_config
from app.services.channels.voice.bolna_service import BolnaService
from app.services.channels.voice.plivo import CallEvent
from app.services.end_user_service import EndUserService
from app.services.orchestrator import ConversationOrchestrator
from app.services.phone_normalizer import normalize_phone

logger = logging.getLogger(__name__)


class VoiceCallHandler:
    """Setup + finalize for a Plivo voice call."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.orchestrator = ConversationOrchestrator(db)
        self.bolna = BolnaService()

    async def handle_inbound_call(
        self,
        agent_id: uuid.UUID,
        call_event: CallEvent,
    ) -> tuple[uuid.UUID, str]:
        """Create a Conversation + ephemeral Bolna agent for an inbound call.

        Persists the Plivo CallUUID and the Bolna agent ID into
        ``Conversation.context`` so the WS handler can look both up later.
        Returns ``(conversation_id, bolna_agent_id)``.
        """
        logger.info(
            "Inbound voice call: agent_id=%s, call_uuid=%s, from=%s",
            agent_id, call_event.call_sid, call_event.from_number,
        )

        # 1. Resolve the EndUser. Phone callers go to ``end_users.phone_number``
        #    (E.164); SIP-Endpoint callers (no DID needed for the demo) go to
        #    ``end_users.external_id``. Anonymous / blank from_number returns
        #    None — start_conversation handles that gracefully.
        raw_from = call_event.from_number
        end_user = await EndUserService(self.db).get_or_create_by_caller(
            agent_id, raw_from,
        )
        end_user_id = end_user.id if end_user else None

        # Match the channel-side dispatch to what we wrote in the EndUser
        # row, so external_user_phone / external_user_id columns align with
        # how this caller is identified going forward.
        if normalize_phone(raw_from):
            ext_phone, ext_id = raw_from, None
        else:
            ext_phone, ext_id = None, (raw_from or None)

        # 2. Create the Conversation via the orchestrator. Identity kwargs
        #    are persisted there (see orchestrator.start_conversation), so
        #    we no longer write them inline below.
        orch_response = await self.orchestrator.start_conversation(
            agent_id,
            end_user_id=end_user_id,
            external_user_phone=ext_phone,
            external_user_id=ext_id,
        )
        conversation_id = orch_response.conversation_id

        # 3. Build the Bolna agent_config from our DB models (language / voice
        #    / Sarvam config / orchestrator base_url injection).
        agent_config = await build_bolna_agent_config(self.db, agent_id)

        # 4. Create the ephemeral Bolna agent (one per call).
        bolna_agent_id = await self.bolna.create_call_agent(
            agent_config=agent_config,
            conversation_id=conversation_id,
            system_prompt="",
        )

        # 5. Stash call metadata on the Conversation. context.call_sid is the
        #    Plivo CallUUID (key name preserved for back-compat). bolna_agent_id
        #    is what voicebot_ws.py reads on WS connect. external_user_phone is
        #    no longer set here — start_conversation owns identity columns now.
        conversation = await self._load_conversation(conversation_id)
        if conversation is not None:
            conversation.context = {
                **(conversation.context or {}),
                "channel": "voice",
                "call_sid": call_event.call_sid,
                "direction": call_event.direction,
                "bolna_agent_id": bolna_agent_id,
            }
            channel = await self._find_voice_channel(agent_id)
            if channel is not None:
                conversation.channel_id = channel.id
            await self.db.flush()

        logger.info(
            "Inbound call ready: conversation_id=%s, bolna_agent_id=%s",
            conversation_id, bolna_agent_id,
        )
        return conversation_id, bolna_agent_id

    async def handle_call_end(
        self,
        conversation_id: uuid.UUID,
        call_event: CallEvent,
    ) -> None:
        """Mark the Conversation COMPLETED and stash final call metadata."""
        logger.info(
            "Voice call end: conversation_id=%s, call_uuid=%s, duration=%s",
            conversation_id, call_event.call_sid, call_event.duration,
        )

        conversation = await self._load_conversation(conversation_id)
        if conversation is None:
            logger.warning("Conversation %s not found during call_end", conversation_id)
            return

        conversation.status = ConversationStatus.COMPLETED
        conversation.ended_at = datetime.now(timezone.utc)
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

    async def _load_conversation(
        self, conversation_id: uuid.UUID,
    ) -> Conversation | None:
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _find_voice_channel(self, agent_id: uuid.UUID) -> Channel | None:
        stmt = select(Channel).where(
            Channel.agent_id == agent_id,
            Channel.channel_type == ChannelType.VOICE,
            Channel.is_active.is_(True),
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()
