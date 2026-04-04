"""Abstract base class for WhatsApp BSP providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.services.channels.whatsapp.types import NormalizedMessage, SendResult


class WhatsAppProviderBase(ABC):
    """Interface that every WhatsApp BSP adapter must implement.

    Concrete implementations (Gupshup, Meta Cloud API, etc.) inherit from
    this class and provide the transport-specific logic.
    """

    @abstractmethod
    async def send_text(self, to: str, text: str) -> SendResult:
        """Send a plain-text WhatsApp message."""
        ...

    @abstractmethod
    async def send_interactive(
        self, to: str, body: str, buttons: list[dict]
    ) -> SendResult:
        """Send a WhatsApp interactive message with quick-reply buttons."""
        ...

    @abstractmethod
    async def send_media(
        self, to: str, media_url: str, caption: str | None = None
    ) -> SendResult:
        """Send an image/document/media message."""
        ...

    @abstractmethod
    async def send_template(
        self, to: str, template_id: str, params: dict
    ) -> SendResult:
        """Send a pre-approved WhatsApp template message."""
        ...

    @abstractmethod
    def parse_webhook(self, payload: dict) -> NormalizedMessage | None:
        """Parse the provider's incoming webhook JSON into a NormalizedMessage.

        Returns ``None`` if the payload is not a user message (e.g. a
        delivery receipt or status update).
        """
        ...

    @abstractmethod
    def verify_webhook(self, signature: str, body: bytes) -> bool:
        """Verify the authenticity of an incoming webhook request."""
        ...
