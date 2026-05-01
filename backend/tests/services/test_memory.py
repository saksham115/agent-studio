"""Tests for the mem0 wrapper (``app.services.memory``).

We mock the cached ``Memory`` instance so the tests don't need a running
Postgres or Pellet API key. The mock is plugged in via
``monkeypatch.setattr("app.services.memory._build_memory", ...)``; the
autouse fixture in ``conftest.py`` clears the lru_cache between tests so
the next test gets a clean Memory.

Coverage:

- ``add_memory`` calls Memory.add with the right shape (kwargs, not metadata).
- ``add_memory`` swallows exceptions and logs.
- ``get_user_memories`` calls Memory.get_all with ``filters`` + ``top_k``,
  not top-level user_id/agent_id (verified against installed mem0 v2.0.1).
- ``get_user_memories`` parses the response and returns ``[memory: str]``.
- ``get_user_memories`` returns ``[]`` on exception.
- Empty / malformed responses yield ``[]``.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services import memory as memory_module


# ---------------------------------------------------------------------------
# add_memory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_memory_calls_mem0_with_right_kwargs(monkeypatch):
    fake = MagicMock()
    fake.add.return_value = {"results": [{"memory": "fact 1"}, {"memory": "fact 2"}]}
    monkeypatch.setattr(memory_module, "_build_memory", lambda: fake)

    eu_id, agent_id = uuid4(), uuid4()
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    await memory_module.add_memory(eu_id, agent_id, msgs)

    fake.add.assert_called_once_with(
        messages=msgs,
        user_id=str(eu_id),
        agent_id=str(agent_id),
    )


@pytest.mark.asyncio
async def test_add_memory_empty_messages_skips_call(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(memory_module, "_build_memory", lambda: fake)
    await memory_module.add_memory(uuid4(), uuid4(), [])
    fake.add.assert_not_called()


@pytest.mark.asyncio
async def test_add_memory_swallows_exceptions(monkeypatch):
    fake = MagicMock()
    fake.add.side_effect = RuntimeError("Pellet credit exhausted")
    monkeypatch.setattr(memory_module, "_build_memory", lambda: fake)

    # Must NOT raise — memory is best-effort, never blocks the request flow.
    await memory_module.add_memory(uuid4(), uuid4(), [{"role": "user", "content": "x"}])
    fake.add.assert_called_once()


# ---------------------------------------------------------------------------
# get_user_memories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_user_memories_uses_filters_and_top_k(monkeypatch):
    """v2.0.1 expects filters dict + top_k, not top-level user_id/agent_id/limit."""
    fake = MagicMock()
    fake.get_all.return_value = {"results": [{"memory": "fact-A"}, {"memory": "fact-B"}]}
    monkeypatch.setattr(memory_module, "_build_memory", lambda: fake)

    eu_id, agent_id = uuid4(), uuid4()
    facts = await memory_module.get_user_memories(eu_id, agent_id, limit=10)

    fake.get_all.assert_called_once_with(
        filters={"user_id": str(eu_id), "agent_id": str(agent_id)},
        top_k=10,
    )
    assert facts == ["fact-A", "fact-B"]


@pytest.mark.asyncio
async def test_get_user_memories_handles_list_response(monkeypatch):
    """Some mem0 versions return a bare list instead of {results: [...]}."""
    fake = MagicMock()
    fake.get_all.return_value = [{"memory": "fact-1"}]
    monkeypatch.setattr(memory_module, "_build_memory", lambda: fake)

    facts = await memory_module.get_user_memories(uuid4(), uuid4())
    assert facts == ["fact-1"]


@pytest.mark.asyncio
async def test_get_user_memories_skips_items_without_memory_field(monkeypatch):
    fake = MagicMock()
    fake.get_all.return_value = {"results": [
        {"memory": "good"},
        {"data": "wrong field"},  # different shape — must skip, not crash
        {"memory": "also good"},
    ]}
    monkeypatch.setattr(memory_module, "_build_memory", lambda: fake)

    facts = await memory_module.get_user_memories(uuid4(), uuid4())
    assert facts == ["good", "also good"]


@pytest.mark.asyncio
async def test_get_user_memories_empty_results(monkeypatch):
    fake = MagicMock()
    fake.get_all.return_value = {"results": []}
    monkeypatch.setattr(memory_module, "_build_memory", lambda: fake)

    facts = await memory_module.get_user_memories(uuid4(), uuid4())
    assert facts == []


@pytest.mark.asyncio
async def test_get_user_memories_swallows_exceptions(monkeypatch):
    fake = MagicMock()
    fake.get_all.side_effect = ConnectionError("psycopg pool exhausted")
    monkeypatch.setattr(memory_module, "_build_memory", lambda: fake)

    facts = await memory_module.get_user_memories(uuid4(), uuid4())
    assert facts == []
