"""Plivo XML response builders.

Plivo XML is a TwiML-derived dialect: ``<Response>`` wraps verbs like ``<Speak>``,
``<Play>``, ``<Stream>``, ``<Record>``, ``<GetDigits>``, ``<Hangup>``. Verbs
execute SEQUENTIALLY (each one completes before the next runs).

Conversation_id is propagated to the WebSocket handler via URL query string —
not via Plivo's ``extraHeaders`` attribute. Bolna's PlivoInputHandler doesn't
parse extraHeaders, and a query-string param always works on the WS side.
"""

from __future__ import annotations

from urllib.parse import quote
from xml.sax.saxutils import escape


def stream_response(
    ws_url: str,
    *,
    content_type: str = "audio/x-l16;rate=8000",
    bidirectional: bool = True,
    keep_call_alive: bool = True,
) -> str:
    """Open a bidirectional WebSocket back to our backend.

    contentType is **linear16 8kHz** (``audio/x-l16;rate=8000``) — NOT mulaw.

    Why: Bolna's upstream Sarvam transcriber, in its plivo branch
    (sarvam_transcriber.py: ``if self.telephony_provider == "plivo": self.encoding = "linear16"``),
    assumes incoming audio is already linear16 — it does NOT call ``audioop.ulaw2lin``.
    If we tell Plivo to send mulaw, Bolna treats the mulaw bytes as linear16
    and forwards garbled audio to Sarvam → zero transcripts (silent demo).

    Plivo accepts asymmetric streams: caller→agent linear16 (this contentType),
    agent→caller mulaw (what Bolna's PlivoOutputHandler emits via playAudio
    ``contentType: audio/x-mulaw``). Plivo handles the codec conversion
    internally on the outbound side.
    """
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response>'
        f'<Stream bidirectional="{str(bidirectional).lower()}" '
        f'keepCallAlive="{str(keep_call_alive).lower()}" '
        f'contentType="{escape(content_type)}">'
        f'{escape(ws_url)}'
        '</Stream>'
        '</Response>'
    )


def say_response(text: str, *, voice: str = "WOMAN", language: str = "en-IN") -> str:
    """Single ``<Speak>`` response — used for "not in service" fallback paths."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Response><Speak voice="{voice}" language="{language}">{escape(text)}</Speak></Response>'
    )


def hangup_response() -> str:
    """Tell Plivo to hang up the call immediately."""
    return '<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>'


def greeting_then_stream(
    *,
    greeting_text: str,
    ws_url: str,
    conversation_id: str,
    language: str = "en-IN",
    voice: str = "WOMAN",
    content_type: str = "audio/x-l16;rate=8000",
) -> str:
    """Demo hedge: speak a short greeting, THEN open the WebSocket stream.

    Plivo XML verbs execute SEQUENTIALLY — ``<Speak>`` finishes before
    ``<Stream>`` opens. Caller-perceived latency is roughly:
    greeting_duration + ~1s WS handshake + Bolna's first turn.

    Keep the greeting short (under ~1s). ``conversation_id`` is appended as a
    query param to the WebSocket URL — voicebot_ws.py reads it from
    ``websocket.query_params`` on connect.
    """
    sep = "&" if "?" in ws_url else "?"
    ws_url_with_id = f"{ws_url}{sep}conversation_id={quote(conversation_id, safe='')}"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response>'
        f'<Speak voice="{voice}" language="{language}">{escape(greeting_text)}</Speak>'
        f'<Stream bidirectional="true" keepCallAlive="true" '
        f'contentType="{escape(content_type)}">'
        f'{escape(ws_url_with_id)}'
        '</Stream>'
        '</Response>'
    )
