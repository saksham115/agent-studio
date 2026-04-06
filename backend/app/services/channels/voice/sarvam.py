"""Sarvam AI STT (Saarika v2) and TTS (Bulbul v2) clients.

Provides async wrappers around the Sarvam AI speech APIs for use in
the voice channel pipeline.
"""

from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TranscriptionResult:
    """Result returned by the Sarvam STT service."""

    text: str
    language: str
    confidence: float | None = None


# ---------------------------------------------------------------------------
# STT client
# ---------------------------------------------------------------------------


class SarvamSTT:
    """Sarvam AI Speech-to-Text (Saarika v2) client.

    Usage::

        stt = SarvamSTT()
        result = await stt.transcribe(audio_bytes, language="hi-IN")
        print(result.text)
    """

    STT_URL = "https://api.sarvam.ai/speech-to-text"
    MODEL = "saarika:v2.5"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.SARVAM_API_KEY

    async def transcribe(
        self,
        audio_data: bytes,
        language: str = "hi-IN",
        audio_format: str = "wav",
    ) -> TranscriptionResult:
        """Transcribe audio bytes to text using Sarvam Saarika v2.

        Args:
            audio_data: Raw audio bytes (WAV, MP3, etc.).
            language: BCP-47 language code (e.g. ``hi-IN``, ``en-IN``).
            audio_format: File extension hint used for the multipart filename.

        Returns:
            A :class:`TranscriptionResult` with the transcript.

        Raises:
            httpx.HTTPStatusError: If the Sarvam API returns an error status.
            ValueError: If the API key is not configured.
        """
        if not self.api_key:
            raise ValueError("SARVAM_API_KEY is not configured")

        headers = {
            "API-Subscription-Key": self.api_key,
        }

        # Build multipart form data
        filename = f"audio.{audio_format}"
        files = {
            "file": (filename, io.BytesIO(audio_data), f"audio/{audio_format}"),
        }
        data = {
            "language_code": language,
            "model": self.MODEL,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            logger.info("Sarvam STT request: language=%s, audio_size=%d bytes", language, len(audio_data))
            response = await client.post(
                self.STT_URL,
                headers=headers,
                files=files,
                data=data,
            )
            if response.status_code != 200:
                logger.error("Sarvam STT error %d: %s", response.status_code, response.text)
            response.raise_for_status()

        result = response.json()
        transcript = result.get("transcript", "")
        detected_language = result.get("language_code", language)

        logger.info(
            "Sarvam STT result: language=%s, transcript_length=%d",
            detected_language,
            len(transcript),
        )

        return TranscriptionResult(
            text=transcript,
            language=detected_language,
            confidence=result.get("confidence"),
        )


# ---------------------------------------------------------------------------
# TTS client
# ---------------------------------------------------------------------------


class SarvamTTS:
    """Sarvam AI Text-to-Speech (Bulbul v2) client.

    Usage::

        tts = SarvamTTS()
        audio_bytes = await tts.synthesize("Namaste!", language="hi-IN")
    """

    TTS_URL = "https://api.sarvam.ai/text-to-speech"
    MODEL = "bulbul:v2"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.SARVAM_API_KEY

    async def synthesize(
        self,
        text: str,
        language: str = "hi-IN",
        speaker: str = "meera",
    ) -> bytes:
        """Convert text to speech audio (WAV bytes) using Sarvam Bulbul v2.

        Args:
            text: The text to synthesize.
            language: BCP-47 target language code.
            speaker: Voice ID (e.g. ``meera``, ``arvind``).

        Returns:
            Raw WAV audio bytes decoded from the base64 API response.

        Raises:
            httpx.HTTPStatusError: If the Sarvam API returns an error status.
            ValueError: If the API key is not configured or the response has no audio.
        """
        if not self.api_key:
            raise ValueError("SARVAM_API_KEY is not configured")

        headers = {
            "API-Subscription-Key": self.api_key,
            "Content-Type": "application/json",
        }

        payload = {
            "inputs": [text],
            "target_language_code": language,
            "speaker": speaker,
            "model": self.MODEL,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            logger.info(
                "Sarvam TTS request: language=%s, speaker=%s, text_length=%d",
                language,
                speaker,
                len(text),
            )
            response = await client.post(
                self.TTS_URL,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

        result = response.json()
        audios = result.get("audios", [])

        if not audios:
            raise ValueError("Sarvam TTS returned no audio data")

        # Decode the first audio segment from base64
        audio_bytes = base64.b64decode(audios[0])
        logger.info("Sarvam TTS result: audio_size=%d bytes", len(audio_bytes))
        return audio_bytes
