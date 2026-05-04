"""OpenAI-compatible chat completions endpoint for Bolna voice calls.

Bolna's LiteLLM sends standard OpenAI-format requests here. We extract
the latest user transcript, route it through our ConversationOrchestrator
(tools, state machine, guardrails, KB), and return the response in
OpenAI format for Bolna to synthesize via TTS.

Conversation mapping: the Bearer token encodes our conversation_id
as ``bolna_{conversation_id}``, set when the Bolna agent is created.

Bolna runs with ``agent_flow_type: "streaming"`` and sends ``stream=true``
on every request. When streaming, we return Server-Sent Events (SSE) in
OpenAI chat.completion.chunk format so Bolna's synthesizer receives the
text as it would from a real OpenAI streaming endpoint.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.database import async_session_factory
from app.models.conversation import Conversation, ConversationStatus
from app.observability import tracer
from app.services.channels.voice.plivo import PlivoClient
from app.services.orchestrator import ConversationOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter()

# Seconds to wait after a terminal-state reply before hanging up the
# Plivo call. The agent's goodbye line needs time to TTS and play out
# before we kill the audio leg — too short and the user hears "advisor
# will call back…" cut off mid-sentence; too long and the user starts
# talking into a dead conversation. 8s is a comfortable middle for
# 2-3 sentence replies; tunable if voice replies grow longer.
TERMINAL_HANGUP_DELAY_S = 8.0

# Module-level set so fire-and-forget asyncio.create_task() instances
# aren't garbage-collected before they finish (Python's loop only holds
# weak refs to tasks). The done-callback discards them on completion.
_pending_hangup_tasks: set[asyncio.Task] = set()

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


@router.post("/chat/completions")
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

    fallback_text = "I didn't catch that. Could you please repeat?"

    if not user_text:
        return _respond(fallback_text, request.stream)

    logger.info(
        "Voice completions: conversation_id=%s, stream=%s, user=%r",
        conversation_id,
        request.stream,
        user_text[:200],
    )

    # Call orchestrator
    with tracer.start_as_current_span("voice.completions") as span:
        span.set_attribute("voice.conversation_id", str(conversation_id))
        span.set_attribute("voice.stream", request.stream)
        span.set_attribute("voice.user_text_length", len(user_text))
        try:
            async with async_session_factory() as db:
                orchestrator = ConversationOrchestrator(db)
                response = await orchestrator.process_message(
                    conversation_id=conversation_id,
                    user_message=VOICE_HINT + user_text,
                )
                await db.commit()
                # If the orchestrator marked the conversation COMPLETED
                # (terminal-state transition), schedule a delayed Plivo
                # hangup so the user hears the goodbye line and then the
                # call drops cleanly — instead of staying open for more
                # utterances that hit the "not active" guard.
                if response.status == ConversationStatus.COMPLETED.value:
                    conv = await db.get(Conversation, conversation_id)
                    call_sid = (conv.context or {}).get("call_sid") if conv else None
                    if call_sid:
                        _schedule_terminal_hangup(conversation_id, call_sid)
                    else:
                        logger.warning(
                            "Conversation %s reached terminal state but no "
                            "call_sid in context — cannot hangup",
                            conversation_id,
                        )
        except Exception:
            logger.exception("Orchestrator failed for conversation %s", conversation_id)
            span.set_attribute("voice.error", True)
            return _respond("Sorry, something went wrong. Please try again.", request.stream)
        span.set_attribute("voice.response_length", len(response.message))

    logger.info(
        "Voice completions response: conversation_id=%s, text=%r",
        conversation_id,
        response.message[:200],
    )

    return _respond(response.message, request.stream)


def _schedule_terminal_hangup(conversation_id: uuid.UUID, call_sid: str) -> None:
    """Fire-and-forget a delayed Plivo hangup for a completed conversation.

    Tracked in ``_pending_hangup_tasks`` so the task isn't GC'd before the
    delay elapses. Idempotent: if the user hangs up first or a concurrent
    completion fires this twice, ``hangup_call`` returns False on the
    second attempt (404 from Plivo) and we just log it.
    """
    task = asyncio.create_task(_delayed_terminal_hangup(conversation_id, call_sid))
    _pending_hangup_tasks.add(task)
    task.add_done_callback(_pending_hangup_tasks.discard)


async def _delayed_terminal_hangup(
    conversation_id: uuid.UUID, call_sid: str,
) -> None:
    """Wait for the goodbye line to play out, then hang up the Plivo leg."""
    try:
        await asyncio.sleep(TERMINAL_HANGUP_DELAY_S)
        ok = await PlivoClient().hangup_call(call_sid)
        logger.info(
            "Terminal-state hangup conversation=%s call_sid=%s after %.1fs: ok=%s",
            conversation_id, call_sid, TERMINAL_HANGUP_DELAY_S, ok,
        )
    except Exception:
        logger.warning(
            "Terminal-state hangup task failed for conversation=%s call_sid=%s",
            conversation_id, call_sid, exc_info=True,
        )


def _respond(content: str, stream: bool):
    """Return either a non-streaming dict or an SSE StreamingResponse."""
    if stream:
        return StreamingResponse(
            _sse_chunks(content),
            media_type="text/event-stream",
        )
    return _non_streaming_body(content)


async def _sse_chunks(content: str):
    """Yield OpenAI-format chat.completion.chunk SSE events.

    We split the orchestrator's response on whitespace so Bolna's
    synthesizer can stream to TTS in small pieces rather than waiting
    for the whole string. The final chunk carries finish_reason=stop.
    """
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    def _frame(delta: dict, finish_reason: str | None = None) -> str:
        payload = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": "orchestrator",
            "choices": [
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": finish_reason,
                }
            ],
        }
        return f"data: {json.dumps(payload)}\n\n"

    # First chunk: role
    yield _frame({"role": "assistant"})

    # Content chunks — split on word boundaries so TTS has natural cut points
    words = content.split(" ")
    buffer = ""
    for i, word in enumerate(words):
        buffer = f"{buffer} {word}" if buffer else word
        # Emit every ~12 words so streaming is visible but not over-fragmented
        if (i + 1) % 12 == 0 or i == len(words) - 1:
            yield _frame({"content": buffer})
            buffer = ""

    if buffer:
        yield _frame({"content": buffer})

    # Final chunk: finish_reason=stop
    yield _frame({}, finish_reason="stop")

    # SSE terminator
    yield "data: [DONE]\n\n"


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


def _non_streaming_body(content: str) -> dict:
    """Format response as non-streaming OpenAI chat.completion object."""
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
