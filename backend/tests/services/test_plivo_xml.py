"""Tests for the Plivo XML response builders.

We don't validate against an XML schema — Plivo doesn't ship one — but we
check that the produced XML is well-formed and contains the expected
attributes / values. The end-to-end demo verifies behavior against real Plivo.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from app.services.channels.voice.plivo_xml import (
    greeting_then_stream,
    hangup_response,
    say_response,
    stream_response,
)


def _parse(xml_str: str) -> ET.Element:
    """Parse XML; raises on malformed output."""
    return ET.fromstring(xml_str)


# ---------------------------------------------------------------------------
# stream_response
# ---------------------------------------------------------------------------


def test_stream_response_contains_expected_attrs():
    xml = stream_response("wss://example/api/v1/voice/ws")
    root = _parse(xml)
    assert root.tag == "Response"
    stream = root.find("Stream")
    assert stream is not None
    assert stream.get("bidirectional") == "true"
    assert stream.get("keepCallAlive") == "true"
    assert stream.get("contentType") == "audio/x-l16;rate=8000"
    assert stream.text == "wss://example/api/v1/voice/ws"


def test_stream_response_disabled_bidirectional():
    xml = stream_response("wss://example", bidirectional=False)
    root = _parse(xml)
    assert root.find("Stream").get("bidirectional") == "false"


# ---------------------------------------------------------------------------
# say_response
# ---------------------------------------------------------------------------


def test_say_response_contains_speak():
    xml = say_response("Hello world")
    root = _parse(xml)
    speak = root.find("Speak")
    assert speak is not None
    assert speak.text == "Hello world"
    assert speak.get("voice") == "WOMAN"


def test_say_response_escapes_special_chars():
    """Ensure < > & in user-supplied text don't break XML parsing."""
    xml = say_response("A & B <test>")
    root = _parse(xml)  # Would raise on malformed XML
    # Text is decoded by parser back to original
    assert root.find("Speak").text == "A & B <test>"


# ---------------------------------------------------------------------------
# hangup_response
# ---------------------------------------------------------------------------


def test_hangup_response_well_formed():
    xml = hangup_response()
    root = _parse(xml)
    assert root.find("Hangup") is not None


# ---------------------------------------------------------------------------
# greeting_then_stream
# ---------------------------------------------------------------------------


def test_greeting_then_stream_speak_before_stream():
    """Verbs execute sequentially — <Speak> must come before <Stream>."""
    xml = greeting_then_stream(
        greeting_text="Connecting you now...",
        ws_url="wss://example/api/v1/voice/ws",
        conversation_id="abc-123",
    )
    root = _parse(xml)
    children = list(root)
    assert len(children) == 2
    assert children[0].tag == "Speak"
    assert children[1].tag == "Stream"


def test_greeting_then_stream_appends_conversation_id_query():
    """conversation_id should be appended as ?conversation_id=… on the WS URL."""
    xml = greeting_then_stream(
        greeting_text="Hi",
        ws_url="wss://example/api/v1/voice/ws",
        conversation_id="abc-123",
    )
    root = _parse(xml)
    stream_url = root.find("Stream").text
    assert "?conversation_id=abc-123" in stream_url


def test_greeting_then_stream_preserves_existing_query():
    """If ws_url already has a query string, append with & not ?."""
    xml = greeting_then_stream(
        greeting_text="Hi",
        ws_url="wss://example/api/v1/voice/ws?debug=1",
        conversation_id="x",
    )
    stream_url = _parse(xml).find("Stream").text
    assert "?debug=1&conversation_id=x" in stream_url


def test_greeting_then_stream_url_encodes_conversation_id():
    """Conversation IDs containing & or = must be URL-encoded."""
    xml = greeting_then_stream(
        greeting_text="Hi",
        ws_url="wss://example",
        conversation_id="foo&bar=baz",
    )
    stream_url = _parse(xml).find("Stream").text
    # The raw "&" / "=" inside the conversation_id must be percent-encoded.
    # XML parsing decodes &amp; → & — so check on the decoded text.
    assert "?conversation_id=foo%26bar%3Dbaz" in stream_url


def test_greeting_then_stream_stream_attrs():
    xml = greeting_then_stream(
        greeting_text="Hi", ws_url="wss://example", conversation_id="x",
    )
    stream = _parse(xml).find("Stream")
    assert stream.get("bidirectional") == "true"
    assert stream.get("keepCallAlive") == "true"
    assert stream.get("contentType") == "audio/x-l16;rate=8000"
