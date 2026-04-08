"""OpenAI-compatible chat completions endpoint for Bolna voice calls.

Bolna's LiteLLM sends standard OpenAI-format requests here. We extract
the latest user transcript, route it through our ConversationOrchestrator
(tools, state machine, guardrails, KB), and return the response in
OpenAI format for Bolna to synthesize via TTS.

Conversation mapping: the Bearer token encodes our conversation_id
as ``bolna_{conversation_id}``, set when the Bolna agent is created.
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.database import async_session_factory
from app.services.orchestrator import ConversationOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter()

# Voice hint prepended to user messages for concise responses
VOICE_HINT = (
    "[VOICE CALL: Keep your response under 2-3 short sentences. "
    "Be conversational and concise — the user is listening, not reading.]\n\n"
)


class ChatMessage(BaseModel):
    role: str
    content: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str = "orchestrator"
    messages: list[ChatMessage] = []
    max_tokens: int = 200
    temperature: float = 0.0
    stream: bool = False


@router.post("/completions")
async def voice_chat_completions(
    request: ChatCompletionRequest,
    authorization: str = Header(None),
):
    """OpenAI-compatible chat completions for Bolna voice pipeline."""

    # Parse conversation_id from Bearer token: "Bearer bolna_{conversation_id}"
    conversation_id = _extract_conversation_id(authorization)
    if not conversation_id:
        raise HTTPException(status_code=401, detail="Invalid authorization token")

    # Extract last user message
    user_text = ""
    for msg in reversed(request.messages):
        if msg.role == "user" and msg.content:
            user_text = msg.content
            break

    if not user_text:
        return _format_response("I didn't catch that. Could you please repeat?")

    logger.info(
        "Voice completions: conversation_id=%s, user=%r",
        conversation_id,
        user_text[:200],
    )

    # Call orchestrator
    try:
        async with async_session_factory() as db:
            orchestrator = ConversationOrchestrator(db)
            response = await orchestrator.process_message(
                conversation_id=conversation_id,
                user_message=VOICE_HINT + user_text,
            )
            await db.commit()
    except Exception:
        logger.exception("Orchestrator failed for conversation %s", conversation_id)
        return _format_response("Sorry, something went wrong. Please try again.")

    logger.info(
        "Voice completions response: conversation_id=%s, text=%r",
        conversation_id,
        response.message[:200],
    )

    return _format_response(response.message)


def _extract_conversation_id(authorization: str | None) -> uuid.UUID | None:
    """Parse conversation_id from Bearer token ``bolna_{uuid}``."""
    if not authorization:
        return None

    token = authorization.removeprefix("Bearer ").strip()
    if not token.startswith("bolna_"):
        return None

    try:
        return uuid.UUID(token[6:])  # strip "bolna_" prefix
    except (ValueError, AttributeError):
        return None


def _format_response(content: str) -> dict:
    """Format response as OpenAI chat.completion object."""
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "orchestrator",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }
