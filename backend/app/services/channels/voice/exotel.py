"""Exotel telephony client for making and receiving voice calls.

Wraps the Exotel REST API for outbound call initiation, status polling,
and inbound webhook parsing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CallResult:
    """Outcome of an outbound call initiation request."""

    success: bool
    call_sid: str | None = None
    error: str | None = None


@dataclass
class CallEvent:
    """Normalised representation of an Exotel call webhook payload."""

    call_sid: str
    from_number: str
    to_number: str
    status: str  # ringing, in-progress, completed, failed, busy, no-answer
    direction: str  # inbound, outbound
    duration: int | None = None
    recording_url: str | None = None


# ---------------------------------------------------------------------------
# Exotel client
# ---------------------------------------------------------------------------


class ExotelClient:
    """Exotel telephony integration for voice calls.

    Usage::

        client = ExotelClient()
        result = await client.make_call(
            from_number="+919876543210",
            to_number="+911234567890",
            caller_id="0402287XXX",
            callback_url="https://example.com/api/v1/webhooks/voice/status",
        )
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_token: str | None = None,
        sid: str | None = None,
        subdomain: str | None = None,
    ) -> None:
        self.api_key = api_key or settings.EXOTEL_API_KEY
        self.api_token = api_token or getattr(settings, "EXOTEL_API_TOKEN", "")
        self.sid = sid or getattr(settings, "EXOTEL_SID", "")
        self.subdomain = subdomain or getattr(settings, "EXOTEL_SUBDOMAIN", "")
        self.base_url = f"https://{self.subdomain}.exotel.com/v1/Accounts/{self.sid}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def make_call(
        self,
        from_number: str,
        to_number: str,
        caller_id: str,
        callback_url: str,
        exoml_app_url: str | None = None,
    ) -> CallResult:
        """Initiate an outbound call via Exotel.

        Args:
            from_number: The number to call from (customer side).
            to_number: The agent-side number or ExoPhone.
            caller_id: Exotel CallerID (ExoPhone number).
            callback_url: URL Exotel will POST status updates to.
            exoml_app_url: Optional ExoML application URL for call flow.

        Returns:
            A :class:`CallResult` with the call SID on success.
        """
        if not self.api_key or not self.api_token:
            raise ValueError("Exotel API credentials are not configured")

        url = f"{self.base_url}/Calls/connect.json"

        form_data = {
            "From": from_number,
            "To": to_number,
            "CallerId": caller_id,
            "StatusCallback": callback_url,
        }
        if exoml_app_url:
            form_data["Url"] = exoml_app_url

        auth = (self.api_key, self.api_token)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.info(
                    "Exotel make_call: from=%s, to=%s, caller_id=%s",
                    from_number,
                    to_number,
                    caller_id,
                )
                response = await client.post(url, data=form_data, auth=auth)
                response.raise_for_status()

            data = response.json()
            print(f"[EXOTEL] make_call response: {data}", flush=True)
            call_data = data.get("Call", {})
            call_sid = call_data.get("Sid", "")

            logger.info("Exotel call initiated: call_sid=%s", call_sid)
            return CallResult(success=True, call_sid=call_sid)

        except httpx.HTTPStatusError as exc:
            error_msg = f"Exotel API error: {exc.response.status_code} - {exc.response.text}"
            logger.error(error_msg)
            return CallResult(success=False, error=error_msg)
        except httpx.RequestError as exc:
            error_msg = f"Exotel request failed: {exc}"
            logger.error(error_msg)
            return CallResult(success=False, error=error_msg)

    async def update_exophone_webhook(self, phone_number: str, voice_url: str) -> bool:
        """Update an ExoPhone's voice URL to point to our webhook."""
        if not self.api_key or not self.api_token:
            return False

        # First, get the ExoPhone SID
        url = f"{self.base_url}/IncomingPhoneNumbers.json"
        auth = (self.api_key, self.api_token)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, auth=auth)
                resp.raise_for_status()
                data = resp.json()

                # Find the SID for this phone number
                single = data.get("IncomingPhoneNumber")
                if single and single.get("PhoneNumber") == phone_number:
                    phone_sid = single["Sid"]
                else:
                    return False

                # Update the voice URL
                update_url = f"{self.base_url}/IncomingPhoneNumbers/{phone_sid}.json"
                update_resp = await client.put(
                    update_url,
                    data={"VoiceUrl": voice_url},
                    auth=auth,
                )
                update_resp.raise_for_status()
                logger.info("Updated ExoPhone %s voice URL to %s", phone_number, voice_url)
                return True
        except Exception:
            logger.exception("Failed to update ExoPhone webhook")
            return False

    async def list_exophones(self) -> list[str]:
        """Fetch all ExoPhone numbers from the Exotel account."""
        if not self.api_key or not self.api_token:
            raise ValueError("Exotel API credentials are not configured")

        url = f"{self.base_url}/IncomingPhoneNumbers.json"
        auth = (self.api_key, self.api_token)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, auth=auth)
                response.raise_for_status()

            data = response.json()
            # Handle both singular and plural response formats
            numbers = data.get("IncomingPhoneNumbers", [])
            if not numbers:
                single = data.get("IncomingPhoneNumber")
                if single and single.get("PhoneNumber"):
                    return [single["PhoneNumber"]]
            return [n.get("PhoneNumber", "") for n in numbers if n.get("PhoneNumber")]
        except Exception:
            logger.exception("Failed to fetch ExoPhones")
            return []

    async def get_call_status(self, call_sid: str) -> dict:
        """Get the status of an ongoing or completed call.

        Args:
            call_sid: The Exotel call SID.

        Returns:
            Raw JSON dict from the Exotel API with call details.
        """
        if not self.api_key or not self.api_token:
            raise ValueError("Exotel API credentials are not configured")

        url = f"{self.base_url}/Calls/{call_sid}.json"
        auth = (self.api_key, self.api_token)

        async with httpx.AsyncClient(timeout=30.0) as client:
            logger.info("Exotel get_call_status: call_sid=%s", call_sid)
            response = await client.get(url, auth=auth)
            response.raise_for_status()

        data = response.json()
        call_data = data.get("Call", data)
        logger.info("Exotel call status: call_sid=%s, status=%s", call_sid, call_data.get("Status"))
        return call_data

    def parse_webhook(self, payload: dict) -> CallEvent:
        """Parse an Exotel webhook payload into a normalised :class:`CallEvent`.

        Exotel sends the following fields in its status-callback and
        incoming-call webhooks:

        - ``CallSid``: Unique call identifier.
        - ``From``: Caller number.
        - ``To``: Called number.
        - ``CallStatus`` / ``Status``: Call state string.
        - ``Direction``: ``inbound`` or ``outbound``.
        - ``Duration``: Call duration in seconds (when completed).
        - ``RecordingUrl``: URL to the call recording (if enabled).

        Args:
            payload: The form/JSON data from the Exotel webhook.

        Returns:
            A populated :class:`CallEvent`.
        """
        call_sid = payload.get("CallSid", payload.get("call_sid", ""))
        from_number = payload.get("From", payload.get("from", ""))
        to_number = payload.get("To", payload.get("to", ""))
        status = payload.get("CallStatus", payload.get("Status", payload.get("status", "unknown")))
        direction = payload.get("Direction", payload.get("direction", "inbound"))

        # Duration may be absent or empty string
        raw_duration = payload.get("Duration", payload.get("duration"))
        duration: int | None = None
        if raw_duration is not None and str(raw_duration).strip():
            try:
                duration = int(raw_duration)
            except (ValueError, TypeError):
                duration = None

        recording_url = payload.get("RecordingUrl", payload.get("recording_url"))

        # Normalise status to lowercase
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
            "Exotel webhook parsed: call_sid=%s, status=%s, direction=%s",
            event.call_sid,
            event.status,
            event.direction,
        )
        return event
