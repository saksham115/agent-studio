"""WhatsApp message handler — bridges incoming WhatsApp messages with the
conversation orchestrator.

Responsible for:
- Finding or creating conversations for a given phone number + agent pair
- Delegating message processing to the orchestrator
- Returning the agent's text response for sending back via WhatsApp
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel, ChannelType
from app.models.conversation import Conversation, ConversationStatus
from app.services.channels.whatsapp.types import NormalizedMessage
from app.services.end_user_service import EndUserService
from app.services.media_processor import MediaProcessor
from app.services.orchestrator import ConversationOrchestrator

logger = logging.getLogger(__name__)


class WhatsAppMessageHandler:
    """Processes incoming WhatsApp messages through the agent orchestrator.

    Usage::

        handler = WhatsAppMessageHandler(db)
        response_text = await handler.handle_incoming(agent_id, normalized_msg)
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.orchestrator = ConversationOrchestrator(db)

    async def handle_incoming(
        self, agent_id: uuid.UUID, message: NormalizedMessage, access_token: str = ""
    ) -> str:
        """Process an incoming WhatsApp message and return the agent's response.

        Flow:
        1. Resolve the EndUser identity from the sender's phone number. Agno
           uses this UUID as ``user_id``, so cross-message memory recall
           works the same way it does on voice.
        2. Find an existing ACTIVE conversation for this end-user. Falls back
           to phone-keyed lookup if EndUser couldn't be resolved (defensive
           guard for malformed sender phones).
        3. If no conversation exists, start one via the orchestrator —
           identity kwargs flow into the Conversation row.
        4. Process media messages.
        5. Pass through the orchestrator (mode="text"; voice_style off).

        Memory writes are NOT scheduled inline here. WhatsApp has no clean
        termination signal (no hangup, no end_session), so the
        ``memory.extract_idle_conversations`` Celery beat task drives the
        write path — it sweeps every 5 min and extracts conversations
        idle past ``MEMORY_IDLE_THRESHOLD_MINUTES`` (default 10), then
        closes them. Memory READ still works for free via the orchestrator's
        ``get_user_memories`` call on every incoming message.
        """
        # -- 1. Resolve EndUser identity ----------------------------------------
        end_user = await EndUserService(self.db).get_or_create_by_caller(
            agent_id, message.sender_phone, name=message.contact_name,
        )
        end_user_id = end_user.id if end_user else None

        # -- 2. Find existing active conversation -------------------------------
        # Prefer the end-user-keyed lookup (hits idx_conversations_end_user_status).
        # Fall back to phone-keyed lookup when EndUser couldn't be resolved
        # (e.g. unparseable sender_phone — rare with WA but defended for safety).
        conversation = None
        if end_user_id is not None:
            conversation = await self._find_active_conversation_by_end_user(end_user_id)
        if conversation is None:
            conversation = await self._find_active_conversation(
                agent_id, message.sender_phone
            )

        # -- 3. Start new conversation if needed --------------------------------
        if conversation is None:
            logger.info(
                "Starting new WhatsApp conversation for agent=%s phone=%s end_user=%s",
                agent_id,
                message.sender_phone,
                end_user_id,
            )
            start_response = await self.orchestrator.start_conversation(
                agent_id,
                end_user_id=end_user_id,
                external_user_phone=message.sender_phone,
                external_user_name=message.contact_name,
            )
            conversation_id = start_response.conversation_id

            # Reload to set the channel link. Identity columns are already
            # written by start_conversation — no inline assignment needed.
            conversation = await self._load_conversation(conversation_id)
            if conversation is None:
                raise RuntimeError(
                    f"Failed to load newly created conversation {conversation_id}"
                )
            channel = await self._find_whatsapp_channel(agent_id)
            if channel:
                conversation.channel_id = channel.id
                await self.db.flush()
        else:
            conversation_id = conversation.id
            # Backfill end_user_id on conversations that pre-date this PR's
            # identity layer (or were started by the legacy phone-keyed
            # path). Idempotent: skips when already set.
            if end_user_id is not None and conversation.end_user_id is None:
                conversation.end_user_id = end_user_id
            # Update contact name if we have a newer one
            if message.contact_name and conversation.external_user_name != message.contact_name:
                conversation.external_user_name = message.contact_name
            await self.db.flush()

        # -- 4. Process media messages ------------------------------------------
        content = message.content
        if message.message_type not in ("text", "button_reply") and message.media_url and access_token:
            logger.info(
                "Processing media type=%s from phone=%s (conversation=%s)",
                message.message_type,
                message.sender_phone,
                conversation_id,
            )
            try:
                processor = MediaProcessor(access_token, agent_id)
                content = await processor.process_media(
                    media_url=message.media_url,
                    media_type=message.message_type,
                    caption=message.caption,
                )
            except Exception:
                logger.exception("Media processing failed, using fallback content")

        # -- 5. Process through orchestrator -----------------------------------
        try:
            response = await self.orchestrator.process_message(
                conversation_id, content
            )
            logger.info(
                "Orchestrator response for conversation=%s: %d chars",
                conversation_id,
                len(response.message),
            )
            return response.message

        except Exception:
            logger.exception(
                "Error processing message for conversation=%s agent=%s",
                conversation_id,
                agent_id,
            )
            return (
                "I'm sorry, I encountered an error processing your message. "
                "Please try again in a moment."
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _find_active_conversation(
        self, agent_id: uuid.UUID, sender_phone: str
    ) -> Conversation | None:
        """Phone-keyed fallback lookup. Used when EndUser resolution fails."""
        stmt = (
            select(Conversation)
            .where(
                Conversation.agent_id == agent_id,
                Conversation.external_user_phone == sender_phone,
                Conversation.status == ConversationStatus.ACTIVE,
            )
            .order_by(Conversation.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _find_active_conversation_by_end_user(
        self, end_user_id: uuid.UUID,
    ) -> Conversation | None:
        """End-user-keyed lookup — primary path post-PR.

        Hits ``idx_conversations_end_user_status`` (composite index from
        alembic 004), so this stays fast even with millions of conversations.
        """
        stmt = (
            select(Conversation)
            .where(
                Conversation.end_user_id == end_user_id,
                Conversation.status == ConversationStatus.ACTIVE,
            )
            .order_by(Conversation.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _load_conversation(
        self, conversation_id: uuid.UUID
    ) -> Conversation | None:
        """Load a conversation by ID."""
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _find_whatsapp_channel(self, agent_id: uuid.UUID) -> Channel | None:
        """Find the WhatsApp channel configured for an agent."""
        stmt = select(Channel).where(
            Channel.agent_id == agent_id,
            Channel.channel_type == ChannelType.WHATSAPP,
            Channel.is_active.is_(True),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
