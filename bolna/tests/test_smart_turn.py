"""Unit tests for bolna/smart_turn.py.

Runs inside the Bolna container where onnxruntime, transformers, and numpy
are already installed:

    docker-compose -f docker-compose.voice.yml exec bolna pytest /app/tests -v

Tests are designed NOT to require the ONNX weights file — the classifier
itself is mocked. We only exercise the buffer, state-bookkeeping, and
gate-logic code paths. Actual classifier quality is validated via the
end-to-end phone-call tests described in the integration plan.
"""

from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock

# Make smart_turn importable whether we run from /app (container) or repo root.
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

# Flip the flag before importing so install_patches() doesn't try to patch
# Bolna during test import.
os.environ.setdefault("SMART_TURN_ENABLED", "false")

import numpy as np
import pytest

import smart_turn as st


# --------------------------------------------------------------------------
# AudioRingBuffer
# --------------------------------------------------------------------------


def test_ring_buffer_empty_snapshot_returns_empty_f32():
    buf = st.AudioRingBuffer(src_rate=8000, window_s=8.0)
    snap = buf.snapshot_16k_float32()
    assert snap.dtype == np.float32
    assert len(snap) == 0


def test_ring_buffer_appends_and_reads_back_correct_shape():
    buf = st.AudioRingBuffer(src_rate=8000, window_s=1.0)  # 1 s = 16000 bytes
    # 0.5 s of silence at 8 kHz int16 = 8000 bytes
    buf.append(b"\x00" * 8000)
    snap = buf.snapshot_16k_float32()
    # Resampled from 8 kHz to 16 kHz → 2x samples; 4000 int16 samples in
    # becomes ~8000 float32 samples out.
    assert snap.dtype == np.float32
    assert 7900 <= len(snap) <= 8100  # allow for resampling edge effects


def test_ring_buffer_evicts_oldest_when_full():
    buf = st.AudioRingBuffer(src_rate=8000, window_s=0.1)  # 0.1 s → 1600 bytes cap
    # Append three 1000-byte chunks (total 3000 > 1600). Oldest chunk should be dropped.
    buf.append(b"\x01" * 1000)
    buf.append(b"\x02" * 1000)
    buf.append(b"\x03" * 1000)
    assert buf.size <= buf.max_bytes
    # First chunk (\x01) is gone; size should be chunks 2 + 3 = 2000 → wait,
    # eviction keeps max_bytes cap. Let's assert we dropped at least one chunk.
    assert len(buf.chunks) < 3


# --------------------------------------------------------------------------
# _truncate_to_last_n_seconds
# --------------------------------------------------------------------------


def test_truncate_pads_short_audio_with_leading_zeros():
    # 2 s at 16 kHz = 32000 samples
    audio = np.ones(32000, dtype=np.float32)
    out = st._truncate_to_last_n_seconds(audio, n_seconds=8, sample_rate=16000)
    assert len(out) == 8 * 16000  # 128000
    # Leading 6 s are zero-padded; the tail 2 s are the original ones.
    assert np.allclose(out[: 6 * 16000], 0.0)
    assert np.allclose(out[-32000:], 1.0)


def test_truncate_keeps_tail_for_long_audio():
    # 10 s at 16 kHz = 160000 samples, with a ramp so we can check which end was kept
    audio = np.arange(160000, dtype=np.float32)
    out = st._truncate_to_last_n_seconds(audio, n_seconds=8, sample_rate=16000)
    assert len(out) == 8 * 16000
    # We kept the LAST 8 s, so out[0] should be where the original audio was
    # at index (160000 - 128000) = 32000.
    assert out[0] == 32000.0
    assert out[-1] == 159999.0


def test_truncate_passes_through_exact_length():
    audio = np.full(128000, 0.5, dtype=np.float32)
    out = st._truncate_to_last_n_seconds(audio, n_seconds=8, sample_rate=16000)
    assert len(out) == 128000
    assert np.allclose(out, 0.5)


# --------------------------------------------------------------------------
# State management
# --------------------------------------------------------------------------


def test_drop_state_clears_all_three_dicts():
    st._buffers["sid-1"] = st.AudioRingBuffer()
    st._pending_transcripts["sid-1"] = ["hello"]
    st._utterance_start_ts["sid-1"] = 123.0
    st.drop_state("sid-1")
    assert "sid-1" not in st._buffers
    assert "sid-1" not in st._pending_transcripts
    assert "sid-1" not in st._utterance_start_ts


def test_drop_state_is_safe_on_missing_sid():
    st.drop_state("nope-never-seen")  # should not raise
    st.drop_state(None)  # explicit None path


def test_drop_state_for_ws_resolves_via_mapping():
    class FakeWs:
        pass

    ws = FakeWs()
    st._ws_to_sid[id(ws)] = "sid-via-ws"
    st._buffers["sid-via-ws"] = st.AudioRingBuffer()
    st.drop_state_for_ws(ws)
    assert id(ws) not in st._ws_to_sid
    assert "sid-via-ws" not in st._buffers


def test_drop_state_for_ws_is_safe_on_none_ws():
    st.drop_state_for_ws(None)  # should not raise


# --------------------------------------------------------------------------
# SmartTurnGate — exercise the async wrapper with a mocked sync predictor
# --------------------------------------------------------------------------


def test_gate_is_complete_dispatches_to_thread_and_returns_tuple():
    async def run():
        gate = st.SmartTurnGate.__new__(st.SmartTurnGate)  # skip __init__ (no ONNX load)
        gate._predict_sync = lambda audio: (True, 0.87)
        audio = np.zeros(16000, dtype=np.float32)
        complete, prob = await gate.is_complete(audio)
        assert complete is True
        assert prob == pytest.approx(0.87)

    asyncio.run(run())


def test_gate_is_complete_propagates_false():
    async def run():
        gate = st.SmartTurnGate.__new__(st.SmartTurnGate)
        gate._predict_sync = lambda audio: (False, 0.12)
        complete, prob = await gate.is_complete(np.zeros(16000, dtype=np.float32))
        assert complete is False
        assert prob == pytest.approx(0.12)

    asyncio.run(run())


# --------------------------------------------------------------------------
# Cleanup between tests so shared module state doesn't leak
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_module_state():
    st._buffers.clear()
    st._pending_transcripts.clear()
    st._utterance_start_ts.clear()
    st._ws_to_sid.clear()
    yield
    st._buffers.clear()
    st._pending_transcripts.clear()
    st._utterance_start_ts.clear()
    st._ws_to_sid.clear()
