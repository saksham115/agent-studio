"""Voice call WebSocket proxy — Plivo → backend → Bolna sidecar.

Plivo's ``<Stream>`` directive opens a bidirectional WebSocket to this endpoint.
The webhook handler in :mod:`webhooks.py` has already created the Conversation
and the ephemeral Bolna agent before Plivo dials in; this module just proxies
audio frames between Plivo and the Bolna sidecar.

The ``conversation_id`` arrives as a URL query parameter (``?conversation_id=…``)
set by ``plivo_xml.greeting_then_stream``. We use it to look up the Conversation
row and extract ``bolna_agent_id`` from ``Conversation.context``.

Defensive 2nd-WS-at-hangup handling: Plivo opens a second WebSocket briefly when
the call ends (Bolna issue #148). If a 2nd connection arrives for a conversation
we're already proxying, we close it immediately rather than letting it spin up
a phantom second proxy.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.models.conversation import Conversation
from app.services.channels.voice.bolna_service import BolnaService

logger = logging.getLogger(__name__)

router = APIRouter()

# In-process set of conversation_ids with an active proxy connection.
# A 2nd WS arriving for the same conversation_id is closed immediately.
# Single-worker dev OK; for multi-worker, a Redis-backed set is the upgrade path.
_active_proxies: set[uuid.UUID] = set()


@router.websocket("/voice/ws")
async def voicebot_websocket(websocket: WebSocket) -> None:
    """Plivo bidirectional audio WebSocket. Pure proxy to Bolna."""
    await websocket.accept()

    raw_id = websocket.query_params.get("conversation_id")
    if not raw_id:
        logger.warning("voicebot_ws: missing conversation_id query param")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    try:
        conversation_id = uuid.UUID(raw_id)
    except ValueError:
        logger.warning("voicebot_ws: invalid conversation_id=%r", raw_id)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Defense against Plivo's 2nd-WS-at-hangup behaviour (Bolna issue #148).
    if conversation_id in _active_proxies:
        logger.info(
            "voicebot_ws: duplicate connection for conversation=%s — closing",
            conversation_id,
        )
        await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
        return

    # Look up Conversation → bolna_agent_id.
    bolna_agent_id: str | None = None
    async with async_session_factory() as db:
        conversation = (await db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )).scalar_one_or_none()
        if conversation is None:
            logger.warning(
                "voicebot_ws: conversation %s not found", conversation_id,
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        bolna_agent_id = (conversation.context or {}).get("bolna_agent_id")

    if not bolna_agent_id:
        logger.warning(
            "voicebot_ws: no bolna_agent_id on conversation=%s; was the answer_url"
            " webhook called first?", conversation_id,
        )
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    _active_proxies.add(conversation_id)
    logger.info(
        "voicebot_ws: connection opened, conversation=%s, bolna_agent=%s",
        conversation_id, bolna_agent_id,
    )

    try:
        await _proxy(websocket, bolna_agent_id, conversation_id)
    except WebSocketDisconnect:
        logger.info("voicebot_ws: client disconnected, conversation=%s", conversation_id)
    except Exception:
        logger.exception(
            "voicebot_ws: error in proxy loop, conversation=%s", conversation_id,
        )
    finally:
        _active_proxies.discard(conversation_id)
        # Clean up the ephemeral Bolna agent. Conversation finalization is
        # handled by the /webhooks/voice/status callback; we only own the
        # Bolna-side cleanup here.
        try:
            await BolnaService().delete_agent(bolna_agent_id)
        except Exception:
            logger.exception(
                "voicebot_ws: failed to delete Bolna agent %s", bolna_agent_id,
            )
        logger.info(
            "voicebot_ws: connection closed, conversation=%s", conversation_id,
        )


async def _proxy(
    client_ws: WebSocket,
    bolna_agent_id: str,
    conversation_id: uuid.UUID,
) -> None:
    """Bidirectional frame proxy between Plivo (client_ws) and Bolna."""
    import websockets

    bolna_ws_url = f"{settings.BOLNA_WS_URL}/chat/v1/{bolna_agent_id}"
    logger.info(
        "voicebot_ws: proxying conversation=%s to %s",
        conversation_id, bolna_ws_url,
    )

    async with websockets.connect(bolna_ws_url) as bolna_ws:
        # Frame counters — logged once at disconnect for diagnostics.
        counts = {"in": 0, "out": 0}

        async def client_to_bolna() -> None:
            try:
                while True:
                    data = await client_ws.receive_text()
                    counts["in"] += 1
                    await bolna_ws.send(data)
            except WebSocketDisconnect:
                await bolna_ws.close()
            except Exception:
                logger.exception("client_to_bolna proxy error")

        async def bolna_to_client() -> None:
            try:
                async for data in bolna_ws:
                    counts["out"] += 1
                    await client_ws.send_text(data)
            except Exception:
                logger.exception("bolna_to_client proxy error")

        try:
            await asyncio.gather(client_to_bolna(), bolna_to_client())
        finally:
            logger.info(
                "voicebot_ws: conv=%s frames in=%d out=%d",
                conversation_id, counts["in"], counts["out"],
            )
