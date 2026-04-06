"""Media processing service for WhatsApp messages.

Downloads media from Meta Graph API, uploads to MinIO, and extracts
content: transcribes voice notes, extracts document text, describes images.
"""

from __future__ import annotations

import logging
import mimetypes
import uuid

import httpx

from app.config import settings
from app.services.storage import StorageService

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


class MediaProcessor:
    """Download, store, and extract content from WhatsApp media."""

    def __init__(self, access_token: str, agent_id: str | uuid.UUID) -> None:
        self.access_token = access_token
        self.agent_id = str(agent_id)
        self.storage = StorageService()

    async def process_media(
        self,
        media_url: str,
        media_type: str,
        caption: str | None = None,
    ) -> str:
        """Download media, store in MinIO, extract content.

        Returns a text representation of the media content suitable
        for passing to the LLM.
        """
        try:
            file_bytes, content_type = await self._download_from_meta(media_url)
        except Exception:
            logger.exception("Failed to download media from %s", media_url)
            return self._fallback_content(media_type, caption)

        # Upload to MinIO
        ext = self._ext_from_content_type(content_type, media_type)
        s3_key = StorageService.generate_media_key(self.agent_id, media_type, f"media.{ext}")
        try:
            self.storage.upload_file(file_bytes, s3_key, content_type)
            logger.info("Stored media at s3://%s (%d bytes)", s3_key, len(file_bytes))
        except Exception:
            logger.exception("Failed to upload media to S3")

        # Extract content based on type
        if media_type == "voice":
            return await self._transcribe_audio(file_bytes, content_type, caption)
        elif media_type == "document":
            return await self._extract_document_text(file_bytes, content_type, caption)
        elif media_type == "image":
            return self._describe_image(caption, s3_key)
        elif media_type == "video":
            return f"[User sent a video]{f': {caption}' if caption else ''}. Please ask them to describe what they want to share."
        else:
            return self._fallback_content(media_type, caption)

    async def _download_from_meta(self, media_url: str) -> tuple[bytes, str]:
        """Download media from Meta Graph API.

        Meta requires a two-step process:
        1. GET the media URL to get the actual download URL
        2. GET the download URL to get the file bytes
        """
        headers = {"Authorization": f"Bearer {self.access_token}"}

        async with httpx.AsyncClient(timeout=30) as client:
            # Step 1: Get the download URL from the media ID endpoint
            meta_resp = await client.get(media_url, headers=headers)
            meta_resp.raise_for_status()
            download_url = meta_resp.json().get("url")

            if not download_url:
                raise ValueError(f"No download URL in Meta response: {meta_resp.json()}")

            # Step 2: Download the actual file
            file_resp = await client.get(download_url, headers=headers)
            file_resp.raise_for_status()

            content_type = file_resp.headers.get("content-type", "application/octet-stream")
            return file_resp.content, content_type

    async def _transcribe_audio(
        self, file_bytes: bytes, content_type: str, caption: str | None
    ) -> str:
        """Transcribe voice note using Sarvam AI Saarika STT."""
        if not settings.SARVAM_API_KEY:
            logger.warning("No SARVAM_API_KEY configured, cannot transcribe voice note")
            return "[User sent a voice message but transcription is not configured]. Ask them to type their message instead."

        try:
            from app.services.channels.voice.sarvam import SarvamSTT

            stt = SarvamSTT()
            ext = self._ext_from_content_type(content_type, "voice")
            result = await stt.transcribe(
                audio_data=file_bytes,
                language="unknown",  # Auto-detect language
                audio_format=ext,
            )

            if not result.text:
                return "[User sent a voice message that could not be transcribed]. Ask them to type their message instead."

            logger.info("Transcribed voice note via Sarvam: %d chars, lang=%s", len(result.text), result.language)
            return f"[Voice message transcription]: {result.text}"

        except Exception:
            logger.exception("Voice transcription failed")
            return "[User sent a voice message but transcription failed]. Ask them to type their message instead."

    async def _extract_document_text(
        self, file_bytes: bytes, content_type: str, caption: str | None
    ) -> str:
        """Extract text from a document using DocumentProcessor."""
        try:
            from app.services.document_processor import DocumentProcessor

            # Map content type to source type
            source_type_map = {
                "application/pdf": "pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
                "text/plain": "txt",
                "text/csv": "csv",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
            }

            ext = self._ext_from_content_type(content_type, "document")
            source_type = source_type_map.get(content_type, ext)
            filename = f"document.{ext}"

            processor = DocumentProcessor()
            chunks = await processor.process_document(file_bytes, filename, source_type)

            if not chunks:
                return f"[User sent a document: {caption or filename}] but no text could be extracted."

            # Combine chunks, limit to ~2000 chars for LLM context
            full_text = "\n".join(c.content for c in chunks)
            if len(full_text) > 2000:
                full_text = full_text[:2000] + "... [truncated]"

            prefix = f"[User shared a document"
            if caption:
                prefix += f" titled '{caption}'"
            prefix += "]. Content:\n"

            logger.info("Extracted %d chars from document", len(full_text))
            return prefix + full_text

        except Exception:
            logger.exception("Document text extraction failed")
            return f"[User sent a document: {caption or 'unknown'}] but it could not be processed. Ask them to describe the content."

    def _describe_image(self, caption: str | None, s3_key: str) -> str:
        """Build a text description for an image message."""
        if caption:
            return f"[User sent an image with caption]: {caption}"
        return "[User sent an image without caption]. Ask them what they'd like to discuss about it."

    @staticmethod
    def _fallback_content(media_type: str, caption: str | None) -> str:
        return f"[User sent a {media_type} message]{f': {caption}' if caption else ''}. Ask them to describe what they want to share."

    @staticmethod
    def _ext_from_content_type(content_type: str, media_type: str) -> str:
        """Derive file extension from content type."""
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if ext:
            return ext.lstrip(".")

        defaults = {
            "voice": "ogg",
            "audio": "ogg",
            "image": "jpg",
            "document": "pdf",
            "video": "mp4",
        }
        return defaults.get(media_type, "bin")
