"""Plivo telephony client.

Replaces the previous Exotel integration. Plivo decouples DIDs from URL config
via an Application object — one Application binds to many DIDs, with the answer
URL set once on the Application rather than per-phone. Inbound MVP only;
outbound (`make_call`) is stubbed for a future PR (DLT registration prerequisite).

The Plivo Python SDK is synchronous; any method that touches `self.client.X`
is wrapped in :func:`asyncio.to_thread` so we don't block the FastAPI event loop.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import plivo
from plivo.utils import validate_v3_signature

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes (provider-agnostic — mirror the previous Exotel shape)
# ---------------------------------------------------------------------------


@dataclass
class CallResult:
    """Outcome of an outbound call initiation request."""

    success: bool
    call_sid: str | None = None
    error: str | None = None


@dataclass
class CallEvent:
    """Normalised representation of a Plivo call webhook payload.

    Field names match the previous Exotel CallEvent so call-site code in
    handler.py / webhooks.py stays unchanged. ``call_sid`` here is Plivo's
    ``CallUUID`` (their unique-per-call identifier).
    """

    call_sid: str
    from_number: str
    to_number: str
    status: str  # ringing, in-progress, completed, failed, busy, no-answer
    direction: str  # inbound, outbound
    duration: int | None = None
    recording_url: str | None = None


# ---------------------------------------------------------------------------
# Plivo client
# ---------------------------------------------------------------------------


class PlivoClient:
    """Plivo telephony integration for voice calls.

    Construction reads creds from :mod:`app.config.settings` if not provided.
    Raises ValueError if creds are missing — fail fast at the entrypoint rather
    than at the first API call.
    """

    def __init__(
        self,
        auth_id: str | None = None,
        auth_token: str | None = None,
    ) -> None:
        self.auth_id = auth_id or settings.PLIVO_AUTH_ID
        self.auth_token = auth_token or settings.PLIVO_AUTH_TOKEN
        if not self.auth_id or not self.auth_token:
            raise ValueError("Plivo credentials are not configured (PLIVO_AUTH_ID / PLIVO_AUTH_TOKEN)")
        self.client = plivo.RestClient(self.auth_id, self.auth_token)

    # ------------------------------------------------------------------
    # Webhook parsing & signature verification (pure-CPU; stay sync)
    # ------------------------------------------------------------------

    def parse_webhook(self, payload: dict) -> CallEvent:
        """Normalise a Plivo webhook payload into a :class:`CallEvent`.

        Plivo's voice webhooks send form-encoded POSTs with these fields:

        - ``CallUUID`` — unique call identifier (Plivo's equivalent of CallSid).
        - ``From`` / ``To`` — caller / called numbers (E.164).
        - ``CallStatus`` — ringing, in-progress, completed, failed, busy, no-answer, canceled.
        - ``Direction`` — inbound / outbound.
        - ``Duration`` / ``BillDuration`` — seconds (only on terminal callbacks).
        - ``HangupCause`` — terminal status detail.
        - ``RecordUrl`` — recording URL (when ``<Record>`` was used).
        """
        call_sid = payload.get("CallUUID", payload.get("call_uuid", ""))
        from_number = payload.get("From", payload.get("from", ""))
        to_number = payload.get("To", payload.get("to", ""))
        status = payload.get("CallStatus", payload.get("Status", payload.get("status", "unknown")))
        direction = payload.get("Direction", payload.get("direction", "inbound"))

        raw_duration = payload.get("Duration", payload.get("BillDuration", payload.get("duration")))
        duration: int | None = None
        if raw_duration is not None and str(raw_duration).strip():
            try:
                duration = int(raw_duration)
            except (ValueError, TypeError):
                duration = None

        recording_url = payload.get("RecordUrl", payload.get("RecordingUrl", payload.get("recording_url")))

        status = status.lower().strip() if status else "unknown"
        direction = direction.lower().strip() if direction else "inbound"

        event = CallEvent(
            call_sid=call_sid,
            from_number=from_number,
            to_number=to_number,
            status=status,
            direction=direction,
            duration=duration,
            recording_url=recording_url,
        )

        logger.info(
            "Plivo webhook parsed: call_sid=%s, status=%s, direction=%s",
            event.call_sid, event.status, event.direction,
        )
        return event

    def verify_signature(
        self,
        *,
        method: str,
        url: str,
        params: dict,
        headers,
    ) -> bool:
        """V3 signature verification.

        Plivo signs the (URL + sorted params + nonce) tuple with HMAC-SHA256
        using the auth token. We verify on every webhook to confirm the request
        is genuinely from Plivo.

        Header lookup is case-insensitive: ASGI lowercases all headers, so a
        ``dict(request.headers)`` dict has lowercase keys, while FastAPI's
        ``Headers`` object is case-insensitive natively. Try both forms.
        """
        def _hget(name: str) -> str | None:
            return headers.get(name) or headers.get(name.lower())

        sig = _hget("X-Plivo-Signature-V3")
        nonce = _hget("X-Plivo-Signature-V3-Nonce")
        if not sig or not nonce:
            return False
        try:
            return validate_v3_signature(
                method=method.upper(),
                uri=url,
                nonce=nonce,
                auth_token=self.auth_token,
                v3_signature=sig,
                params=params,
            )
        except Exception:
            logger.exception("Plivo signature verification raised")
            return False

    # ------------------------------------------------------------------
    # SDK calls (sync; wrapped in to_thread for async callers)
    # ------------------------------------------------------------------

    async def get_call_status(self, call_sid: str) -> dict | None:
        """Fetch call metadata via the Plivo REST API.

        Wraps the sync SDK in ``asyncio.to_thread`` so the event loop isn't
        blocked. Returns None if the call doesn't exist or the request fails.
        """
        def _fetch():
            try:
                return self.client.calls.get(call_sid).__dict__
            except plivo.exceptions.PlivoRestError as e:
                logger.warning("Plivo get_call_status failed for %s: %s", call_sid, e)
                return None

        return await asyncio.to_thread(_fetch)

    async def make_call(
        self,
        from_number: str,
        to_number: str,
        answer_url: str,
        hangup_url: str | None = None,
    ) -> CallResult:
        """Initiate an outbound call via Plivo.

        **Stubbed for MVP** — outbound to Indian phones requires DLT registration
        (TRAI UCC 2018 — Principal Entity, content/consent templates). The MVP
        is inbound-only. Wiring this is a follow-up once DLT lands.
        """
        return CallResult(
            success=False,
            error=(
                "Outbound calling not enabled in MVP. "
                "Requires DLT registration before Indian outbound is permitted."
            ),
        )
