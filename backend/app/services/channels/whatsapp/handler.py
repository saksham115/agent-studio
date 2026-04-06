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

from app.models.conversation import Conversation, ConversationStatus
from app.services.channels.whatsapp.types import NormalizedMessage
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
        1. Look up an existing ACTIVE conversation for this phone + agent pair.
        2. If none exists, start a new conversation via the orchestrator.
        3. Set external user metadata on the conversation.
        4. Pass the message content to the orchestrator for processing.
        5. Return the orchestrator's response text.
        """
        # -- 1. Find existing active conversation for this sender + agent ------
        conversation = await self._find_active_conversation(
            agent_id, message.sender_phone
        )

        # -- 2. Start new conversation if needed ------------------------------
        if conversation is None:
            logger.info(
                "Starting new WhatsApp conversation for agent=%s phone=%s",
                agent_id,
                message.sender_phone,
            )
            start_response = await self.orchestrator.start_conversation(agent_id)
            conversation_id = start_response.conversation_id

            # Reload the conversation so we can set metadata on it
            conversation = await self._load_conversation(conversation_id)
            if conversation is None:
                raise RuntimeError(
                    f"Failed to load newly created conversation {conversation_id}"
                )

            # -- 3. Set external user metadata ---------------------------------
            conversation.external_user_phone = message.sender_phone
            conversation.external_user_name = message.contact_name
            await self.db.flush()
        else:
            conversation_id = conversation.id
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
        """Find an existing active conversation for the given agent + phone."""
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

    async def _load_conversation(
        self, conversation_id: uuid.UUID
    ) -> Conversation | None:
        """Load a conversation by ID."""
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
