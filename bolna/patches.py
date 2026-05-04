"""Bolna Sarvam STT/TTS instrumentation patches.

Adds two manual spans per voice turn so Honeycomb shows STT and TTS latency
alongside the backend's ``voice.completions`` LLM span:

- ``bolna.stt.turn`` — opens at Sarvam VAD START_SPEECH, closes at END_SPEECH.
  Carries ``stt.first_result_latency_ms`` (time from speech-end to first
  transcript word) and ``stt.duration_ms`` (total turn duration).
- ``bolna.tts.first_chunk`` — opens when a text chunk is first sent to the
  Sarvam TTS WebSocket for a turn, closes when the first audio chunk comes
  back. Measures TTS time-to-first-byte.

These plug a gap Saksham's commit explicitly left open: per-stage
transcriber/synthesizer spans require Bolna internal patches. We're done
patching now — monkey-patch at runtime, no Bolna fork needed.
"""

from __future__ import annotations

import logging
import time

from opentelemetry import trace

logger = logging.getLogger(__name__)

_tracer = trace.get_tracer("agent-studio-bolna")


def patch_bolna_for_tracing() -> None:
    """Install STT/TTS span instrumentation on Bolna's Sarvam classes.

    Call once after Bolna imports are loaded but before the first call comes
    in. Safe to call multiple times — the patch is idempotent (we tag the
    class with a sentinel attribute on first patch).
    """
    try:
        from bolna.transcriber.sarvam_transcriber import SarvamTranscriber

        _patch_sarvam_transcriber(SarvamTranscriber)
    except Exception:
        logger.exception("patches: failed to wrap SarvamTranscriber.receiver")

    try:
        from bolna.synthesizer.sarvam_synthesizer import SarvamSynthesizer

        _patch_sarvam_synthesizer(SarvamSynthesizer)
    except Exception:
        logger.exception("patches: failed to wrap SarvamSynthesizer")


def _patch_sarvam_transcriber(cls) -> None:
    if getattr(cls, "_otel_patched", False):
        return
    original_receiver = cls.receiver

    async def traced_receiver(self, ws):
        turn_start_wall: float | None = None
        turn_first_result_wall: float | None = None
        async for packet in original_receiver(self, ws):
            try:
                data = packet.get("data") if isinstance(packet, dict) else packet
                if data == "speech_started":
                    turn_start_wall = time.time()
                    turn_first_result_wall = None
                elif (
                    isinstance(data, dict)
                    and data.get("type") == "interim_transcript_received"
                    and turn_first_result_wall is None
                ):
                    turn_first_result_wall = time.time()
                elif data == "speech_ended" and turn_start_wall is not None:
                    end_wall = time.time()
                    duration_ms = int((end_wall - turn_start_wall) * 1000)
                    span = _tracer.start_span(
                        "bolna.stt.turn",
                        start_time=int(turn_start_wall * 1e9),
                    )
                    span.set_attribute("stt.duration_ms", duration_ms)
                    if turn_first_result_wall is not None:
                        ttfr_ms = int(
                            (turn_first_result_wall - turn_start_wall) * 1000
                        )
                        span.set_attribute("stt.first_result_latency_ms", ttfr_ms)
                    span.end(end_time=int(end_wall * 1e9))
                    turn_start_wall = None
                    turn_first_result_wall = None
            except Exception:
                logger.exception("patches: stt receiver instrumentation error")
            yield packet

    cls.receiver = traced_receiver
    cls._otel_patched = True
    logger.info("patches: SarvamTranscriber.receiver wrapped (bolna.stt.turn)")


def _patch_sarvam_synthesizer(cls) -> None:
    if getattr(cls, "_otel_patched", False):
        return
    original_sender = cls.sender
    original_receiver = cls.receiver

    async def traced_sender(self, text, sequence_id, end_of_llm_stream=False):
        # First non-empty text chunk for a TTS turn marks the request start.
        # Reset (in receiver) when first audio chunk arrives so the next turn
        # gets its own send-start time.
        if text and getattr(self, "_otel_tts_send_time", None) is None:
            self._otel_tts_send_time = time.time()
        return await original_sender(self, text, sequence_id, end_of_llm_stream)

    async def traced_receiver(self):
        async for chunk in original_receiver(self):
            try:
                send_time = getattr(self, "_otel_tts_send_time", None)
                # Skip the b"\x00" terminator the synthesizer yields after
                # last_text_sent — only count real audio chunks for TTFB.
                is_audio = (
                    isinstance(chunk, (bytes, bytearray))
                    and len(chunk) > 1
                )
                if send_time is not None and is_audio:
                    end_time = time.time()
                    ttfb_ms = int((end_time - send_time) * 1000)
                    span = _tracer.start_span(
                        "bolna.tts.first_chunk",
                        start_time=int(send_time * 1e9),
                    )
                    span.set_attribute("tts.first_chunk_ms", ttfb_ms)
                    span.end(end_time=int(end_time * 1e9))
                    self._otel_tts_send_time = None
            except Exception:
                logger.exception("patches: tts receiver instrumentation error")
            yield chunk

    cls.sender = traced_sender
    cls.receiver = traced_receiver
    cls._otel_patched = True
    logger.info(
        "patches: SarvamSynthesizer.sender/receiver wrapped (bolna.tts.first_chunk)"
    )
