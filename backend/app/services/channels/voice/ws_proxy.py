"""WebSocket proxy that replays buffered messages.

We read the initial 'connected' and 'start' events from Exotel to
extract call metadata before handing the WebSocket to Bolna. This
wrapper replays those messages so Bolna sees them too.
"""

from __future__ import annotations


class ReplayableWebSocket:
    """Wraps a FastAPI WebSocket to replay buffered messages."""

    def __init__(self, websocket, buffered_messages: list[str]):
        self._ws = websocket
        self._buffer = list(buffered_messages)

    async def receive_text(self) -> str:
        if self._buffer:
            return self._buffer.pop(0)
        return await self._ws.receive_text()

    async def send_text(self, data: str) -> None:
        return await self._ws.send_text(data)

    async def close(self, *args, **kwargs) -> None:
        return await self._ws.close(*args, **kwargs)
