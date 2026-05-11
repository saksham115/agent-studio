"""Tests for the Agno-backed memory wrapper (``app.services.memory``).

Mocks ``_get_components`` to return a fake (db, mm) pair so tests don't
need a real Agno install, Postgres connection, or LLM credits.

Coverage:
- ``add_memory`` returns True on success, False on exception.
- ``add_memory`` empties → True (trivially successful no-op).
- ``add_memory`` translates dict messages → ``agno.models.message.Message``.
- ``add_memory`` calls ``acreate_user_memories`` with the right shape.
- ``get_user_memories`` calls ``aget_user_memories``, filters by agent_id.
- ``get_user_memories`` sorts newest-first; respects ``limit``.
- ``get_user_memories`` returns ``[]`` on exception.
- Both spans omit ``end_user_id`` (PII), include ``agent_id`` + ``model.*``.
- The per-loop singleton stored via ``setattr(loop, _LOOP_SLOT, ...)`` is
  rebuilt when the running loop changes — verified across two
  ``asyncio.run()`` invocations.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services import memory as memory_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_components(create_returns=None, get_returns=None,
                     create_raises=None, get_raises=None):
    """Build a (db, mm) pair where mm exposes async create/get_user_memories."""
    mm = MagicMock()
    if create_raises is not None:
        mm.acreate_user_memories = AsyncMock(side_effect=create_raises)
    else:
        mm.acreate_user_memories = AsyncMock(return_value=create_returns or "OK")
    if get_raises is not None:
        mm.aget_user_memories = AsyncMock(side_effect=get_raises)
    else:
        mm.aget_user_memories = AsyncMock(return_value=get_returns or [])
    db = MagicMock()
    return db, mm


def _user_memory(memory_text, agent_id, updated_at=1000):
    return SimpleNamespace(memory=memory_text, agent_id=str(agent_id),
                           updated_at=updated_at, memory_id="m")


# ---------------------------------------------------------------------------
# add_memory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_memory_returns_true_on_success(monkeypatch):
    db, mm = _fake_components()
    fake_get = AsyncMock(return_value=(db, mm))
    monkeypatch.setattr(memory_module, "_get_components", fake_get)

    eu, ag = uuid4(), uuid4()
    ok = await memory_module.add_memory(
        eu, ag, [{"role": "user", "content": "hi"}],
    )
    assert ok is True

    mm.acreate_user_memories.assert_awaited_once()
    call = mm.acreate_user_memories.call_args
    assert call.kwargs["user_id"] == str(eu)
    assert call.kwargs["agent_id"] == str(ag)
    # Messages translated to agno.models.message.Message.
    msgs = call.kwargs["messages"]
    assert len(msgs) == 1
    assert msgs[0].role == "user"
    assert msgs[0].content == "hi"


@pytest.mark.asyncio
async def test_add_memory_empty_messages_is_success(monkeypatch):
    fake_get = AsyncMock(side_effect=AssertionError("should not be called"))
    monkeypatch.setattr(memory_module, "_get_components", fake_get)

    ok = await memory_module.add_memory(uuid4(), uuid4(), [])
    assert ok is True
    fake_get.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_memory_returns_false_on_exception(monkeypatch):
    _, mm = _fake_components(create_raises=RuntimeError("Pellet 503"))
    fake_get = AsyncMock(return_value=(None, mm))
    monkeypatch.setattr(memory_module, "_get_components", fake_get)

    ok = await memory_module.add_memory(
        uuid4(), uuid4(), [{"role": "user", "content": "x"}],
    )
    assert ok is False  # caller uses this to skip memory_written_at write


# ---------------------------------------------------------------------------
# get_user_memories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_user_memories_filters_by_agent_id(monkeypatch):
    eu = uuid4()
    ag = uuid4()
    other_ag = uuid4()

    _, mm = _fake_components(get_returns=[
        _user_memory("fact-A", ag, updated_at=100),
        _user_memory("fact-B", other_ag, updated_at=200),  # different agent → drop
        _user_memory("fact-C", ag, updated_at=150),
    ])
    monkeypatch.setattr(memory_module, "_get_components",
                        AsyncMock(return_value=(None, mm)))

    facts = await memory_module.get_user_memories(eu, ag)
    # fact-C (150) is newer than fact-A (100) → fact-C first.
    assert facts == ["fact-C", "fact-A"]


@pytest.mark.asyncio
async def test_get_user_memories_respects_limit(monkeypatch):
    ag = uuid4()
    _, mm = _fake_components(get_returns=[
        _user_memory(f"f-{i}", ag, updated_at=i) for i in range(50)
    ])
    monkeypatch.setattr(memory_module, "_get_components",
                        AsyncMock(return_value=(None, mm)))

    facts = await memory_module.get_user_memories(uuid4(), ag, limit=5)
    assert len(facts) == 5
    # Newest 5 by updated_at descending.
    assert facts == ["f-49", "f-48", "f-47", "f-46", "f-45"]


@pytest.mark.asyncio
async def test_get_user_memories_returns_empty_list_on_exception(monkeypatch):
    _, mm = _fake_components(get_raises=ConnectionError("pool gone"))
    monkeypatch.setattr(memory_module, "_get_components",
                        AsyncMock(return_value=(None, mm)))
    facts = await memory_module.get_user_memories(uuid4(), uuid4())
    assert facts == []


@pytest.mark.asyncio
async def test_get_user_memories_handles_none_response(monkeypatch):
    _, mm = _fake_components(get_returns=None)
    monkeypatch.setattr(memory_module, "_get_components",
                        AsyncMock(return_value=(None, mm)))
    facts = await memory_module.get_user_memories(uuid4(), uuid4())
    assert facts == []


# ---------------------------------------------------------------------------
# Spans — agent_id present, end_user_id ABSENT (PII protection)
# ---------------------------------------------------------------------------


class _SpanCaptureTracer:
    """Minimal tracer that records span name + attributes."""

    def __init__(self):
        self.spans: list[tuple[str, dict]] = []

    def start_as_current_span(self, name):
        attrs: dict = {}
        outer = self

        class _Span:
            def __enter__(self_inner):
                return self_inner
            def __exit__(self_inner, *a):
                outer.spans.append((name, dict(attrs)))
                return False
            def set_attribute(self_inner, k, v):
                attrs[k] = v
            def set_attributes(self_inner, kvs):
                attrs.update(kvs)
        return _Span()


@pytest.mark.asyncio
async def test_memory_add_span_excludes_end_user_id(monkeypatch):
    capture = _SpanCaptureTracer()
    monkeypatch.setattr(memory_module, "tracer", capture)
    _, mm = _fake_components()
    monkeypatch.setattr(memory_module, "_get_components",
                        AsyncMock(return_value=(None, mm)))

    eu, ag = uuid4(), uuid4()
    await memory_module.add_memory(
        eu, ag, [{"role": "user", "content": "test"}],
    )
    span_name, attrs = capture.spans[-1]
    assert span_name == "memory.add"
    assert "end_user_id" not in attrs, f"PII leaked into span: {attrs}"
    assert attrs.get("agent_id") == str(ag)
    assert "model.provider" in attrs
    assert "model.id" in attrs
    assert attrs.get("success") is True


@pytest.mark.asyncio
async def test_memory_get_span_excludes_end_user_id(monkeypatch):
    capture = _SpanCaptureTracer()
    monkeypatch.setattr(memory_module, "tracer", capture)
    _, mm = _fake_components(get_returns=[])
    monkeypatch.setattr(memory_module, "_get_components",
                        AsyncMock(return_value=(None, mm)))

    await memory_module.get_user_memories(uuid4(), uuid4())
    span_name, attrs = capture.spans[-1]
    assert span_name == "memory.get"
    assert "end_user_id" not in attrs


# ---------------------------------------------------------------------------
# Per-loop singleton — rebuilds when the event loop changes
# ---------------------------------------------------------------------------


def test_per_loop_singleton_rebuilds_across_asyncio_run(monkeypatch):
    """Simulates Celery's per-task ``asyncio.run()`` pattern.

    The (db, mm) pair lives on the running loop via ``setattr(loop, slot)``.
    Two distinct ``asyncio.run()`` invocations create two distinct loops;
    each call to ``_get_components`` must construct a fresh pair (or, since
    the second loop has no slot yet, the build path runs again).
    """
    constructions: list[str] = []

    def fake_build_model():
        constructions.append("model")
        return SimpleNamespace()

    monkeypatch.setattr(memory_module, "_build_extraction_model", fake_build_model)

    # Monkey-patch the agno classes so the constructor doesn't hit real DB.
    class FakeDb:
        def __init__(self, **kwargs):
            constructions.append("db")

    class FakeMM:
        def __init__(self, **kwargs):
            constructions.append("mm")

    monkeypatch.setattr("agno.db.postgres.AsyncPostgresDb", FakeDb)
    monkeypatch.setattr("agno.memory.MemoryManager", FakeMM)

    async def acquire():
        await memory_module._get_components()
        await memory_module._get_components()  # same loop → cached
        return None

    asyncio.run(acquire())
    first_count = list(constructions)

    asyncio.run(acquire())
    second_count = list(constructions)

    # Each asyncio.run() creates a fresh loop → fresh singleton build.
    # Within one loop the second call is cached (no extra builds).
    assert second_count.count("mm") == 2, second_count  # one per loop
    assert second_count.count("db") == 2, second_count
