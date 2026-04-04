"""Gupshup BSP adapter for WhatsApp messaging.

Implements the :class:`WhatsAppProviderBase` interface using the Gupshup
Enterprise WhatsApp API (https://docs.gupshup.io/docs/whatsapp-api).

Key endpoints:
- Send message: POST https://api.gupshup.io/wa/api/v1/msg
  Content-Type: application/x-www-form-urlencoded
  Auth: ``apikey`` header

- Incoming webhook: JSON payload with ``payload.type``, ``payload.sender``,
  ``payload.payload`` nested structure.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

from app.services.channels.whatsapp.provider import WhatsAppProviderBase
from app.services.channels.whatsapp.types import NormalizedMessage, SendResult

logger = logging.getLogger(__name__)

# Gupshup API base URL for sending messages.
GUPSHUP_SEND_URL = "https://api.gupshup.io/wa/api/v1/msg"


class GupshupAdapter(WhatsAppProviderBase):
    """Gupshup WhatsApp Business API adapter.

    Parameters
    ----------
    api_key:
        Gupshup API key (sent via the ``apikey`` header).
    app_name:
        The Gupshup app/source name registered on the dashboard.
    source_phone:
        The WhatsApp business phone number registered with Gupshup
        (including country code, no ``+`` prefix).
    webhook_secret:
        Optional shared secret used to verify incoming webhook signatures.
    """

    def __init__(
        self,
        api_key: str,
        app_name: str,
        source_phone: str,
        webhook_secret: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.app_name = app_name
        self.source_phone = source_phone
        self.webhook_secret = webhook_secret
        self.send_url = GUPSHUP_SEND_URL

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def send_text(self, to: str, text: str) -> SendResult:
        """Send a plain-text WhatsApp message via Gupshup."""
        message_payload = json.dumps({"type": "text", "text": text})
        return await self._send(to, message_payload)

    async def send_interactive(
        self, to: str, body: str, buttons: list[dict]
    ) -> SendResult:
        """Send a WhatsApp interactive quick-reply message.

        ``buttons`` should be a list of dicts like::

            [{"id": "opt_1", "title": "Yes"}, {"id": "opt_2", "title": "No"}]

        Gupshup supports up to 3 quick-reply buttons per message.
        """
        # Build Gupshup interactive quick-reply payload
        quick_replies = []
        for btn in buttons[:3]:  # WhatsApp allows max 3 quick-reply buttons
            quick_replies.append(
                {
                    "type": "text",
                    "title": btn.get("title", btn.get("text", "")),
                }
            )

        message_payload = json.dumps(
            {
                "type": "quick_reply",
                "content": {"type": "text", "text": body},
                "options": quick_replies,
            }
        )
        return await self._send(to, message_payload)

    async def send_media(
        self, to: str, media_url: str, caption: str | None = None
    ) -> SendResult:
        """Send an image message with an optional caption."""
        payload_dict: dict[str, Any] = {
            "type": "image",
            "originalUrl": media_url,
            "previewUrl": media_url,
        }
        if caption:
            payload_dict["caption"] = caption

        message_payload = json.dumps(payload_dict)
        return await self._send(to, message_payload)

    async def send_template(
        self, to: str, template_id: str, params: dict
    ) -> SendResult:
        """Send a pre-approved WhatsApp template message.

        ``params`` should contain the template parameter values, e.g.::

            {"1": "John", "2": "your order #1234"}
        """
        # Build Gupshup template payload
        template_params = [
            {"default": value} for value in params.values()
        ]

        message_payload = json.dumps(
            {
                "id": template_id,
                "params": template_params,
            }
        )

        form_data = {
            "channel": "whatsapp",
            "source": self.source_phone,
            "destination": to,
            "template": message_payload,
            "src.name": self.app_name,
        }

        return await self._post(form_data)

    # ------------------------------------------------------------------
    # Webhook parsing
    # ------------------------------------------------------------------

    def parse_webhook(self, payload: dict) -> NormalizedMessage | None:
        """Parse a Gupshup incoming webhook payload into a NormalizedMessage.

        Gupshup webhook structure::

            {
              "app": "MyApp",
              "timestamp": 1234567890,
              "version": 2,
              "type": "message",
              "payload": {
                "id": "msg-id",
                "source": "919876543210",
                "type": "text",
                "payload": {
                  "text": "Hello"
                },
                "sender": {
                  "phone": "919876543210",
                  "name": "John",
                  "country_code": "91",
                  "dial_code": "9876543210"
                }
              }
            }

        Returns ``None`` for non-message events (delivery receipts, status
        updates, etc.).
        """
        # Only process actual user messages
        event_type = payload.get("type", "")
        if event_type not in ("message", "sandbox-message"):
            logger.debug("Ignoring non-message webhook event: %s", event_type)
            return None

        msg_payload = payload.get("payload")
        if not msg_payload:
            logger.warning("Webhook payload missing 'payload' key")
            return None

        # Extract sender information
        sender_info = msg_payload.get("sender", {})
        sender_phone = sender_info.get("phone") or msg_payload.get("source", "")
        contact_name = sender_info.get("name")

        # Message type and content
        message_type = msg_payload.get("type", "text")
        inner_payload = msg_payload.get("payload", {})

        # Normalize content based on message type
        content = ""
        media_url: str | None = None
        caption: str | None = None

        if message_type == "text":
            content = inner_payload.get("text", "")
        elif message_type == "image":
            media_url = inner_payload.get("url", "")
            caption = inner_payload.get("caption", "")
            content = caption or "[Image received]"
        elif message_type == "document":
            media_url = inner_payload.get("url", "")
            caption = inner_payload.get("caption", inner_payload.get("filename", ""))
            content = caption or "[Document received]"
        elif message_type in ("audio", "voice"):
            media_url = inner_payload.get("url", "")
            content = "[Voice message received]"
            message_type = "voice"
        elif message_type == "location":
            lat = inner_payload.get("latitude", "")
            lon = inner_payload.get("longitude", "")
            content = f"[Location: {lat}, {lon}]"
        elif message_type == "button_reply":
            # User tapped a quick-reply button
            content = inner_payload.get("title", inner_payload.get("text", ""))
        else:
            content = inner_payload.get("text", f"[{message_type} message received]")

        if not sender_phone:
            logger.warning("Could not extract sender phone from webhook payload")
            return None

        return NormalizedMessage(
            sender_phone=sender_phone,
            message_id=msg_payload.get("id", ""),
            content=content,
            message_type=message_type,
            media_url=media_url,
            caption=caption,
            timestamp=str(payload.get("timestamp", "")),
            contact_name=contact_name,
        )

    def verify_webhook(self, signature: str, body: bytes) -> bool:
        """Verify the authenticity of a Gupshup webhook request.

        Gupshup uses a shared-secret HMAC-SHA256 signature for webhook
        verification. If no ``webhook_secret`` was configured, verification
        is skipped (returns ``True``).
        """
        if not self.webhook_secret:
            # No secret configured — skip verification
            return True

        expected = hmac.new(
            self.webhook_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _send(self, to: str, message_payload: str) -> SendResult:
        """Build standard form data and POST to Gupshup."""
        form_data = {
            "channel": "whatsapp",
            "source": self.source_phone,
            "destination": to,
            "message": message_payload,
            "src.name": self.app_name,
        }
        return await self._post(form_data)

    async def _post(self, form_data: dict) -> SendResult:
        """Execute the HTTP POST to Gupshup and parse the response."""
        headers = {
            "apikey": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.send_url,
                    data=form_data,
                    headers=headers,
                )

            if response.status_code == 200 or response.status_code == 202:
                body = response.json()
                message_id = body.get("messageId", body.get("id", ""))
                logger.info(
                    "Gupshup message sent successfully: %s -> %s (id=%s)",
                    self.source_phone,
                    form_data.get("destination"),
                    message_id,
                )
                return SendResult(success=True, message_id=str(message_id))
            else:
                error_msg = f"Gupshup API error {response.status_code}: {response.text}"
                logger.error(error_msg)
                return SendResult(success=False, error=error_msg)

        except httpx.TimeoutException:
            error_msg = "Gupshup API request timed out"
            logger.error(error_msg)
            return SendResult(success=False, error=error_msg)
        except httpx.HTTPError as exc:
            error_msg = f"Gupshup HTTP error: {exc}"
            logger.error(error_msg, exc_info=True)
            return SendResult(success=False, error=error_msg)
        except Exception as exc:
            error_msg = f"Unexpected error sending Gupshup message: {exc}"
            logger.error(error_msg, exc_info=True)
            return SendResult(success=False, error=error_msg)
