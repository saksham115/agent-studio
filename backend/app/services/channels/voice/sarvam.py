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

        # Sarvam limits input to 500 chars — split long text into chunks
        # and concatenate the resulting audio.
        MAX_CHARS = 480
        text_chunks = self._split_text(text, MAX_CHARS)

        async with httpx.AsyncClient(timeout=30.0) as client:
            all_audio: list[bytes] = []

            for i, chunk_text in enumerate(text_chunks):
                logger.info(
                    "Sarvam TTS request: language=%s, speaker=%s, chunk=%d/%d, text_length=%d",
                    language, speaker, i + 1, len(text_chunks), len(chunk_text),
                )
                payload = {
                    "inputs": [chunk_text],
                    "target_language_code": language,
                    "speaker": speaker,
                    "model": self.MODEL,
                }
                response = await client.post(
                    self.TTS_URL,
                    headers=headers,
                    json=payload,
                )
                if response.status_code != 200:
                    logger.error("Sarvam TTS error %d: %s", response.status_code, response.text)
                response.raise_for_status()

                result = response.json()
                audios = result.get("audios", [])
                if not audios:
                    raise ValueError("Sarvam TTS returned no audio data")

                all_audio.append(base64.b64decode(audios[0]))

        # Concatenate WAV files — use the header from the first chunk
        # and append raw PCM from subsequent chunks.
        if len(all_audio) == 1:
            combined = all_audio[0]
        else:
            combined = self._concat_wav(all_audio)

        logger.info("Sarvam TTS result: audio_size=%d bytes (%d chunks)", len(combined), len(text_chunks))
        return combined

    @staticmethod
    def _split_text(text: str, max_chars: int) -> list[str]:
        """Split text at sentence boundaries to stay within max_chars."""
        if len(text) <= max_chars:
            return [text]

        chunks: list[str] = []
        remaining = text

        while remaining:
            if len(remaining) <= max_chars:
                chunks.append(remaining)
                break

            # Try to split at sentence boundary (। or . or ? or !)
            split_at = -1
            for sep in ("। ", ". ", "? ", "! ", ", "):
                idx = remaining.rfind(sep, 0, max_chars)
                if idx > 0 and idx > split_at:
                    split_at = idx + len(sep)

            if split_at <= 0:
                # No sentence boundary — split at last space
                split_at = remaining.rfind(" ", 0, max_chars)
            if split_at <= 0:
                # No space — hard split
                split_at = max_chars

            chunks.append(remaining[:split_at].strip())
            remaining = remaining[split_at:].strip()

        return [c for c in chunks if c]

    @staticmethod
    def _concat_wav(wav_parts: list[bytes]) -> bytes:
        """Concatenate multiple WAV files into one by appending PCM data."""
        import struct as st

        if not wav_parts:
            return b""

        # Use the first WAV's header as the base
        header = wav_parts[0][:44]
        pcm_parts = []
        for wav in wav_parts:
            if wav[:4] == b"RIFF" and len(wav) > 44:
                pcm_parts.append(wav[44:])
            else:
                pcm_parts.append(wav)

        combined_pcm = b"".join(pcm_parts)

        # Rebuild WAV header with correct sizes
        buf = bytearray(header)
        st.pack_into("<I", buf, 4, 36 + len(combined_pcm))  # RIFF chunk size
        st.pack_into("<I", buf, 40, len(combined_pcm))  # data chunk size
        return bytes(buf) + combined_pcm
