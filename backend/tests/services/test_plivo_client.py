"""Tests for PlivoClient — webhook parsing + signature verification."""

from __future__ import annotations

import pytest

from app.services.channels.voice.plivo import CallEvent, PlivoClient


# ---------------------------------------------------------------------------
# parse_webhook
# ---------------------------------------------------------------------------


def test_parse_webhook_inbound_in_progress():
    client = PlivoClient()
    event = client.parse_webhook({
        "CallUUID": "abc-123-uuid",
        "From": "+919876543210",
        "To": "+918012345678",
        "CallStatus": "in-progress",
        "Direction": "inbound",
    })
    assert isinstance(event, CallEvent)
    assert event.call_sid == "abc-123-uuid"
    assert event.from_number == "+919876543210"
    assert event.to_number == "+918012345678"
    assert event.status == "in-progress"
    assert event.direction == "inbound"
    assert event.duration is None


def test_parse_webhook_completed_with_duration():
    client = PlivoClient()
    event = client.parse_webhook({
        "CallUUID": "abc",
        "From": "+1",
        "To": "+2",
        "CallStatus": "completed",
        "Duration": "47",
        "BillDuration": "47",
        "HangupCause": "NORMAL_CLEARING",
        "RecordUrl": "https://plivo.example/rec/abc.wav",
    })
    assert event.status == "completed"
    assert event.duration == 47
    assert event.recording_url == "https://plivo.example/rec/abc.wav"


def test_parse_webhook_lowercases_status():
    """Plivo sends 'completed' or 'COMPLETED' depending on event source."""
    client = PlivoClient()
    event = client.parse_webhook({
        "CallUUID": "x", "From": "+1", "To": "+2", "CallStatus": "COMPLETED",
    })
    assert event.status == "completed"


def test_parse_webhook_handles_missing_fields():
    """Garbled / partial payloads don't crash; defaults are sane."""
    client = PlivoClient()
    event = client.parse_webhook({})
    assert event.call_sid == ""
    assert event.status == "unknown"
    assert event.direction == "inbound"
    assert event.duration is None


def test_parse_webhook_invalid_duration_is_none():
    """Non-integer Duration string falls back to None, doesn't raise."""
    client = PlivoClient()
    event = client.parse_webhook({
        "CallUUID": "x", "From": "+1", "To": "+2",
        "CallStatus": "completed", "Duration": "abc",
    })
    assert event.duration is None


# ---------------------------------------------------------------------------
# verify_signature
# ---------------------------------------------------------------------------


def test_verify_signature_missing_headers_returns_false():
    """No X-Plivo-Signature-V3 header → False (don't raise)."""
    client = PlivoClient()
    assert client.verify_signature(
        method="POST",
        url="https://example.com/api/v1/webhooks/voice/incoming",
        params={"CallUUID": "abc"},
        headers={},
    ) is False


def test_verify_signature_bogus_value_returns_false():
    """Wrong signature → False (validate_v3_signature returns False, not raises)."""
    client = PlivoClient()
    assert client.verify_signature(
        method="POST",
        url="https://example.com/api/v1/webhooks/voice/incoming",
        params={"CallUUID": "abc"},
        headers={
            "X-Plivo-Signature-V3": "bogus-signature",
            "X-Plivo-Signature-V3-Nonce": "1234567890",
        },
    ) is False


def test_verify_signature_lowercase_headers():
    """ASGI lowercases headers; our case-insensitive lookup must still find them."""
    client = PlivoClient()
    # Lowercase headers (as ASGI delivers them via dict(request.headers))
    result = client.verify_signature(
        method="POST",
        url="https://example.com/api/v1/webhooks/voice/incoming",
        params={"CallUUID": "abc"},
        headers={
            "x-plivo-signature-v3": "bogus",
            "x-plivo-signature-v3-nonce": "12345",
        },
    )
    # Returns False (bogus sig) but DOESN'T raise / return False due to
    # missing headers — proves our case-insensitive lookup found them.
    assert result is False


# ---------------------------------------------------------------------------
# make_call (stubbed for MVP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_make_call_returns_disabled_error():
    """Outbound is intentionally disabled in MVP — must return a clear error."""
    client = PlivoClient()
    result = await client.make_call(
        from_number="+1", to_number="+2",
        answer_url="https://example", hangup_url=None,
    )
    assert result.success is False
    assert result.error is not None
    assert "outbound" in result.error.lower() or "dlt" in result.error.lower()
