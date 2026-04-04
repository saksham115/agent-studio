"""Common types for WhatsApp channel integration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class NormalizedMessage:
    """Normalized incoming WhatsApp message."""

    sender_phone: str
    message_id: str
    content: str
    message_type: str  # text, image, document, voice
    media_url: str | None = None
    caption: str | None = None
    timestamp: str | None = None
    contact_name: str | None = None


@dataclass
class OutgoingMessage:
    """Message to send via WhatsApp."""

    to_phone: str
    content: str
    message_type: str = "text"  # text, image, document, interactive
    media_url: str | None = None
    buttons: list[dict] | None = None


@dataclass
class SendResult:
    """Result of sending a WhatsApp message."""

    success: bool
    message_id: str | None = None
    error: str | None = None
