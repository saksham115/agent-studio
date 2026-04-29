"""Semantic turn detection via pipecat-ai/smart-turn-v3.

Inserts an 8M-parameter ONNX classifier between Bolna's Sarvam "final
transcript" event and the LLM-fire step. On "incomplete thought" we
accumulate the partial transcript and wait for more audio; on
"complete" we fire the LLM with the full accumulated text.

The predict logic is a minimal reimplementation of pipecat-ai/smart-turn's
`inference.py` and `audio_utils.py`. Upstream: BSD-2-Clause, Daily Inc.
https://github.com/pipecat-ai/smart-turn
"""

from __future__ import annotations

import asyncio
import audioop
import logging
import os
import time
from collections import deque
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Config (all env-driven; SMART_TURN_ENABLED=false keeps native Bolna path)
# --------------------------------------------------------------------------

SMART_TURN_ENABLED = os.getenv("SMART_TURN_ENABLED", "false").lower() == "true"
SMART_TURN_WINDOW_S = float(os.getenv("SMART_TURN_WINDOW_S", "8.0"))
SMART_TURN_MIN_UTT_MS = int(os.getenv("SMART_TURN_MIN_UTT_MS", "600"))
SMART_TURN_FAILOPEN = os.getenv("SMART_TURN_FAILOPEN", "true").lower() == "true"
SMART_TURN_MODEL_PATH = os.getenv(
    "SMART_TURN_MODEL_PATH", "/opt/smart-turn/smart-turn-v3.2-cpu.onnx"
)


# --------------------------------------------------------------------------
# Audio helpers
# --------------------------------------------------------------------------


def _truncate_to_last_n_seconds(
    audio: np.ndarray, n_seconds: int = 8, sample_rate: int = 16000
) -> np.ndarray:
    """Keep the last ``n_seconds`` of audio; left-pad with zeros if shorter.

    Mirrors smart-turn's ``audio_utils.truncate_audio_to_last_n_seconds``.
    """
    max_samples = n_seconds * sample_rate
    if len(audio) > max_samples:
        return audio[-max_samples:]
    if len(audio) < max_samples:
        padding = max_samples - len(audio)
        return np.pad(audio, (padding, 0), mode="constant", constant_values=0)
    return audio


class AudioRingBuffer:
    """Rolling PCM buffer. Stores raw 8 kHz linear16 from Exotel; upsamples
    to 16 kHz float32 at read time (what the classifier wants).

    Sized by window-seconds × sample-rate × 2 bytes/sample (int16).
    """

    def __init__(self, src_rate: int = 8000, window_s: float = SMART_TURN_WINDOW_S):
        self.src_rate = src_rate
        self.max_bytes = int(window_s * src_rate * 2)
        self.chunks: deque[bytes] = deque()
        self.size = 0

    def append(self, pcm_bytes: bytes) -> None:
        self.chunks.append(pcm_bytes)
        self.size += len(pcm_bytes)
        while self.size > self.max_bytes and self.chunks:
            dropped = self.chunks.popleft()
            self.size -= len(dropped)

    def snapshot_16k_float32(self) -> np.ndarray:
        if not self.chunks:
            return np.zeros(0, dtype=np.float32)
        raw = b"".join(self.chunks)
        up, _ = audioop.ratecv(raw, 2, 1, self.src_rate, 16000, None)
        return np.frombuffer(up, dtype=np.int16).astype(np.float32) / 32768.0


# --------------------------------------------------------------------------
# Per-call state (keyed by Exotel stream_sid)
# --------------------------------------------------------------------------

_buffers: dict[str, AudioRingBuffer] = {}
_pending_transcripts: dict[str, list[str]] = {}
_utterance_start_ts: dict[str, float] = {}
# Bridge: websocket object id → stream_sid, so server.py can clean up per-call
# state in its `finally` block without reaching into Bolna internals.
_ws_to_sid: dict[int, str] = {}


def get_or_create_buffer(sid: str) -> AudioRingBuffer:
    return _buffers.setdefault(sid, AudioRingBuffer())


def drop_state(sid: Optional[str]) -> None:
    """Teardown all per-call state for a given ``sid``. Safe if not present."""
    if not sid:
        return
    _buffers.pop(sid, None)
    _pending_transcripts.pop(sid, None)
    _utterance_start_ts.pop(sid, None)


def drop_state_for_ws(ws) -> None:
    """Resolve a websocket to its sid (populated by ingest_audio_patched) and
    drop the per-call state. Used by server.py's websocket teardown."""
    if ws is None:
        return
    sid = _ws_to_sid.pop(id(ws), None)
    drop_state(sid)


# --------------------------------------------------------------------------
# Classifier
# --------------------------------------------------------------------------


class SmartTurnGate:
    """Thread-safe lazy-loaded singleton wrapping smart-turn-v3 ONNX inference."""

    _instance: Optional["SmartTurnGate"] = None
    _lock = asyncio.Lock()

    def __init__(self):
        # Imports here so `import smart_turn` stays cheap when the flag is off.
        import onnxruntime as ort
        from transformers import WhisperFeatureExtractor

        so = ort.SessionOptions()
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        so.inter_op_num_threads = 1
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self._session = ort.InferenceSession(SMART_TURN_MODEL_PATH, sess_options=so)
        self._feature_extractor = WhisperFeatureExtractor(chunk_length=8)
        log.info("smart-turn-v3 loaded from %s", SMART_TURN_MODEL_PATH)

    @classmethod
    async def get(cls) -> "SmartTurnGate":
        async with cls._lock:
            if cls._instance is None:
                # ONNX session load can take 1–2 s; run in a thread so event
                # loop isn't blocked during startup.
                cls._instance = await asyncio.to_thread(cls)
            return cls._instance

    def _predict_sync(self, audio: np.ndarray) -> tuple[bool, float]:
        audio = _truncate_to_last_n_seconds(audio, n_seconds=8)
        inputs = self._feature_extractor(
            audio,
            sampling_rate=16000,
            return_tensors="np",
            padding="max_length",
            max_length=8 * 16000,
            truncation=True,
            do_normalize=True,
        )
        input_features = inputs.input_features.squeeze(0).astype(np.float32)
        input_features = np.expand_dims(input_features, axis=0)
        outputs = self._session.run(None, {"input_features": input_features})
        probability = float(outputs[0][0].item())
        return probability > 0.5, probability

    async def is_complete(self, audio: np.ndarray) -> tuple[bool, float]:
        return await asyncio.to_thread(self._predict_sync, audio)


async def warm_up() -> None:
    """Call from FastAPI startup to pay ONNX init cost before the first call."""
    if SMART_TURN_ENABLED:
        await SmartTurnGate.get()


# --------------------------------------------------------------------------
# Monkey-patches (installed from bolna/server.py at module import time)
# --------------------------------------------------------------------------


def install_patches() -> None:
    """Install smart-turn patches into Bolna. Idempotent; no-op when disabled."""
    if not SMART_TURN_ENABLED:
        log.info("smart-turn disabled (SMART_TURN_ENABLED != true); native Bolna behavior")
        return

    from bolna.input_handlers.telephony import TelephonyInputHandler
    from bolna.agent_manager.task_manager import TaskManager

    # ── Patch 1: capture inbound PCM frames into a per-sid ring buffer ────
    orig_ingest = TelephonyInputHandler.ingest_audio

    async def ingest_audio_patched(self, audio_data, meta_info):
        try:
            sid = getattr(self, "stream_sid", None) or meta_info.get("stream_sid")
            if sid and isinstance(audio_data, (bytes, bytearray)):
                get_or_create_buffer(sid).append(bytes(audio_data))
                _utterance_start_ts.setdefault(sid, time.time())
                # Map this handler's websocket to its sid for teardown later.
                ws = getattr(self, "websocket", None)
                if ws is not None:
                    _ws_to_sid[id(ws)] = sid
        except Exception as exc:
            log.warning("ring-buffer append failed: %s", exc)
        return await orig_ingest(self, audio_data, meta_info)

    TelephonyInputHandler.ingest_audio = ingest_audio_patched

    # ── Patch 2: gate LLM-fire on smart-turn + accumulate partial transcripts ──
    orig_handle = TaskManager._handle_transcriber_output

    async def handle_transcriber_output_patched(
        self, next_task, transcriber_message, meta_info
    ):
        # Only gate the LLM path. Synthesizer / other tasks pass through.
        if next_task != "llm":
            return await orig_handle(self, next_task, transcriber_message, meta_info)

        sid = meta_info.get("stream_sid") or getattr(
            self.tools.get("input"), "stream_sid", None
        )
        transcript = (transcriber_message or "").strip()
        if not sid or not transcript:
            return await orig_handle(self, next_task, transcriber_message, meta_info)

        utt_start = _utterance_start_ts.get(sid, time.time())
        utt_ms = (time.time() - utt_start) * 1000

        # Very short utterances ("yes", "ok") skip the classifier — silence-based
        # signal is already correct for those, and padding tiny clips to 8 s is
        # mostly zeros, which confuses the model.
        if utt_ms < SMART_TURN_MIN_UTT_MS:
            return await orig_handle(self, next_task, transcriber_message, meta_info)

        try:
            buf = _buffers.get(sid)
            if not buf or buf.size == 0:
                return await orig_handle(self, next_task, transcriber_message, meta_info)

            audio = buf.snapshot_16k_float32()
            gate = await SmartTurnGate.get()
            complete, prob = await gate.is_complete(audio)

            # Accumulate any partials that were previously swallowed so the
            # LLM eventually sees the full accumulated thought.
            pending = _pending_transcripts.get(sid, [])
            accumulated = " ".join(pending + [transcript]).strip()

            log.info(
                "[smart-turn] sid=%s complete=%s p=%.3f utt_ms=%.0f accumulated=%r",
                sid, complete, prob, utt_ms, accumulated,
            )

            if complete:
                _pending_transcripts.pop(sid, None)
                _utterance_start_ts.pop(sid, None)
                return await orig_handle(self, next_task, accumulated, meta_info)

            _pending_transcripts[sid] = pending + [transcript]
            return
        except Exception as exc:
            log.warning(
                "smart-turn gate error (fail-open=%s): %s", SMART_TURN_FAILOPEN, exc
            )
            if SMART_TURN_FAILOPEN:
                _pending_transcripts.pop(sid, None)
                return await orig_handle(self, next_task, transcriber_message, meta_info)
            raise

    TaskManager._handle_transcriber_output = handle_transcriber_output_patched

    log.info("smart-turn patches installed")
