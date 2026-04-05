"""Meta WhatsApp Cloud API adapter.

Implements the :class:`WhatsAppProviderBase` interface using the Meta
(Facebook) WhatsApp Cloud API directly, without a third-party BSP.

Key endpoints:
- Send message: POST https://graph.facebook.com/v21.0/{phone_number_id}/messages
  Authorization: Bearer {access_token}
  Content-Type: application/json

- Incoming webhook: nested JSON structure under
  ``entry[].changes[].value.messages[]``

- Webhook verification: HMAC-SHA256 of raw body with ``app_secret``.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import httpx

from app.services.channels.whatsapp.provider import WhatsAppProviderBase
from app.services.channels.whatsapp.types import NormalizedMessage, SendResult

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


class MetaCloudAdapter(WhatsAppProviderBase):
    """Meta WhatsApp Cloud API direct integration.

    Parameters
    ----------
    access_token:
        System User permanent token (or temporary token for testing).
    phone_number_id:
        The Phone Number ID from the Meta Developer Dashboard.
    app_secret:
        Meta App secret used for webhook signature verification.
    verify_token:
        Custom string used during the initial webhook URL verification
        handshake with Meta.
    """

    def __init__(
        self,
        access_token: str,
        phone_number_id: str,
        app_secret: str | None = None,
        verify_token: str | None = None,
    ) -> None:
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.app_secret = app_secret
        self.verify_token = verify_token
        self.api_url = f"{GRAPH_API_BASE}/{phone_number_id}/messages"

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def send_text(self, to: str, text: str) -> SendResult:
        """Send a plain-text WhatsApp message via Meta Cloud API."""
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }
        return await self._post(payload)

    async def send_interactive(
        self, to: str, body: str, buttons: list[dict]
    ) -> SendResult:
        """Send a WhatsApp interactive message with quick-reply buttons.

        ``buttons`` should be a list of dicts like::

            [{"id": "opt_1", "title": "Yes"}, {"id": "opt_2", "title": "No"}]

        Meta supports up to 3 quick-reply buttons per message.
        """
        reply_buttons: list[dict[str, Any]] = []
        for idx, btn in enumerate(buttons[:3]):
            reply_buttons.append(
                {
                    "type": "reply",
                    "reply": {
                        "id": btn.get("id", f"btn_{idx}"),
                        "title": btn.get("title", btn.get("text", ""))[:20],
                    },
                }
            )

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body},
                "action": {"buttons": reply_buttons},
            },
        }
        return await self._post(payload)

    async def send_media(
        self, to: str, media_url: str, caption: str | None = None
    ) -> SendResult:
        """Send an image message with an optional caption."""
        image_obj: dict[str, str] = {"link": media_url}
        if caption:
            image_obj["caption"] = caption

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "image",
            "image": image_obj,
        }
        return await self._post(payload)

    async def send_template(
        self, to: str, template_id: str, params: dict
    ) -> SendResult:
        """Send a pre-approved WhatsApp template message.

        ``params`` should contain the template parameter values, e.g.::

            {"1": "John", "2": "your order #1234"}
        """
        body_parameters = [
            {"type": "text", "text": str(value)} for value in params.values()
        ]

        components: list[dict[str, Any]] = []
        if body_parameters:
            components.append(
                {"type": "body", "parameters": body_parameters}
            )

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_id,
                "language": {"code": "en"},
                "components": components,
            },
        }
        return await self._post(payload)

    # ------------------------------------------------------------------
    # Webhook parsing
    # ------------------------------------------------------------------

    def parse_webhook(self, payload: dict) -> NormalizedMessage | None:
        """Parse a Meta Cloud API incoming webhook payload.

        Meta's webhook structure::

            {
              "object": "whatsapp_business_account",
              "entry": [{
                "id": "BUSINESS_ACCOUNT_ID",
                "changes": [{
                  "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                      "phone_number_id": "xxx",
                      "display_phone_number": "xxx"
                    },
                    "contacts": [{
                      "profile": {"name": "Sender Name"},
                      "wa_id": "919876543210"
                    }],
                    "messages": [{
                      "from": "919876543210",
                      "id": "wamid.xxx",
                      "timestamp": "1234567890",
                      "type": "text",
                      "text": {"body": "Hello"}
                    }]
                  },
                  "field": "messages"
                }]
              }]
            }

        Returns ``None`` for non-message events (delivery receipts, status
        updates, reactions, read receipts, etc.).
        """
        # Ensure this is a WhatsApp Business Account webhook
        if payload.get("object") != "whatsapp_business_account":
            logger.debug(
                "Ignoring non-WhatsApp webhook object: %s",
                payload.get("object"),
            )
            return None

        entries = payload.get("entry", [])
        if not entries:
            logger.debug("Webhook payload has no entries")
            return None

        # Process only the first entry / first change
        changes = entries[0].get("changes", [])
        if not changes:
            logger.debug("Webhook entry has no changes")
            return None

        change = changes[0]
        if change.get("field") != "messages":
            logger.debug("Ignoring non-messages field: %s", change.get("field"))
            return None

        value = change.get("value", {})

        # Check for messages (as opposed to status updates)
        messages = value.get("messages")
        if not messages:
            # This is likely a status update (delivered, read, etc.)
            statuses = value.get("statuses")
            if statuses:
                logger.debug(
                    "Ignoring status update: %s",
                    statuses[0].get("status") if statuses else "unknown",
                )
            else:
                logger.debug("No messages in webhook value — ignoring")
            return None

        msg = messages[0]
        msg_type = msg.get("type", "")

        # Skip non-content message types
        if msg_type in ("reaction", "system", "ephemeral", "order"):
            logger.debug("Ignoring message type: %s", msg_type)
            return None

        # Extract contact info
        contacts = value.get("contacts", [])
        contact_name: str | None = None
        if contacts:
            profile = contacts[0].get("profile", {})
            contact_name = profile.get("name")

        sender_phone = msg.get("from", "")
        message_id = msg.get("id", "")
        timestamp = msg.get("timestamp", "")

        # Normalize content based on message type
        content = ""
        media_url: str | None = None
        caption: str | None = None
        normalized_type = msg_type

        if msg_type == "text":
            content = msg.get("text", {}).get("body", "")

        elif msg_type == "image":
            image_data = msg.get("image", {})
            caption = image_data.get("caption")
            # Meta provides a media ID that must be fetched separately.
            # Store the ID as a placeholder — the handler can download it.
            media_id = image_data.get("id", "")
            media_url = f"{GRAPH_API_BASE}/{media_id}" if media_id else None
            content = caption or "[Image received]"

        elif msg_type == "document":
            doc_data = msg.get("document", {})
            caption = doc_data.get("caption") or doc_data.get("filename")
            media_id = doc_data.get("id", "")
            media_url = f"{GRAPH_API_BASE}/{media_id}" if media_id else None
            content = caption or "[Document received]"

        elif msg_type in ("audio", "voice"):
            audio_data = msg.get("audio", msg.get("voice", {}))
            media_id = audio_data.get("id", "")
            media_url = f"{GRAPH_API_BASE}/{media_id}" if media_id else None
            content = "[Voice message received]"
            normalized_type = "voice"

        elif msg_type == "video":
            video_data = msg.get("video", {})
            caption = video_data.get("caption")
            media_id = video_data.get("id", "")
            media_url = f"{GRAPH_API_BASE}/{media_id}" if media_id else None
            content = caption or "[Video received]"

        elif msg_type == "location":
            loc = msg.get("location", {})
            lat = loc.get("latitude", "")
            lon = loc.get("longitude", "")
            content = f"[Location: {lat}, {lon}]"

        elif msg_type == "interactive":
            interactive = msg.get("interactive", {})
            interactive_type = interactive.get("type", "")
            if interactive_type == "button_reply":
                reply = interactive.get("button_reply", {})
                content = reply.get("title", reply.get("id", ""))
            elif interactive_type == "list_reply":
                reply = interactive.get("list_reply", {})
                content = reply.get("title", reply.get("id", ""))
            else:
                content = f"[Interactive {interactive_type} received]"
            normalized_type = "text"

        elif msg_type == "button":
            # Template button reply (postback)
            content = msg.get("button", {}).get("text", "")
            normalized_type = "text"

        elif msg_type == "sticker":
            sticker_data = msg.get("sticker", {})
            media_id = sticker_data.get("id", "")
            media_url = f"{GRAPH_API_BASE}/{media_id}" if media_id else None
            content = "[Sticker received]"

        elif msg_type == "contacts":
            content = "[Contact card received]"

        else:
            content = f"[{msg_type} message received]"

        if not sender_phone:
            logger.warning(
                "Could not extract sender phone from Meta webhook payload"
            )
            return None

        return NormalizedMessage(
            sender_phone=sender_phone,
            message_id=message_id,
            content=content,
            message_type=normalized_type,
            media_url=media_url,
            caption=caption,
            timestamp=timestamp,
            contact_name=contact_name,
        )

    # ------------------------------------------------------------------
    # Webhook signature verification
    # ------------------------------------------------------------------

    def verify_webhook(self, signature: str, body: bytes) -> bool:
        """Verify the authenticity of a Meta webhook request.

        Meta sends an ``X-Hub-Signature-256`` header with the value
        ``sha256={hex_digest}``.  The digest is an HMAC-SHA256 hash of
        the raw request body using the ``app_secret`` as key.

        If no ``app_secret`` was configured, verification is skipped
        (returns ``True``).
        """
        if not self.app_secret:
            # No secret configured — skip verification
            return True

        # Strip the "sha256=" prefix if present
        if signature.startswith("sha256="):
            signature = signature[len("sha256="):]

        expected = hmac.new(
            self.app_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _post(self, json_payload: dict) -> SendResult:
        """Execute the HTTP POST to Meta Graph API and parse the response."""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.api_url,
                    json=json_payload,
                    headers=headers,
                )

            if response.status_code in (200, 201):
                body = response.json()
                messages = body.get("messages", [])
                message_id = messages[0]["id"] if messages else ""
                logger.info(
                    "Meta Cloud API message sent successfully: %s -> %s (id=%s)",
                    self.phone_number_id,
                    json_payload.get("to"),
                    message_id,
                )
                return SendResult(success=True, message_id=message_id)
            else:
                error_body = response.text
                try:
                    error_json = response.json()
                    error_detail = error_json.get("error", {})
                    error_msg = (
                        f"Meta Cloud API error {response.status_code}: "
                        f"[{error_detail.get('code', '')}] "
                        f"{error_detail.get('message', error_body)}"
                    )
                except Exception:
                    error_msg = (
                        f"Meta Cloud API error {response.status_code}: "
                        f"{error_body}"
                    )
                logger.error(error_msg)
                return SendResult(success=False, error=error_msg)

        except httpx.TimeoutException:
            error_msg = "Meta Cloud API request timed out"
            logger.error(error_msg)
            return SendResult(success=False, error=error_msg)
        except httpx.HTTPError as exc:
            error_msg = f"Meta Cloud API HTTP error: {exc}"
            logger.error(error_msg, exc_info=True)
            return SendResult(success=False, error=error_msg)
        except Exception as exc:
            error_msg = f"Unexpected error sending Meta Cloud API message: {exc}"
            logger.error(error_msg, exc_info=True)
            return SendResult(success=False, error=error_msg)
