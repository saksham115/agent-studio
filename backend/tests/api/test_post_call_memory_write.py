"""Tests for ``webhooks._post_call_memory_write`` — the BackgroundTask helper.

This is the only thing standing between a call ending and mem0 receiving
the message stream, so the contract has to be solid:

- Only USER + ASSISTANT messages get forwarded (SYSTEM/TOOL are filtered).
- Messages are forwarded in chronological order.
- Empty conversations are silent no-ops (no mem0 call).
- mem0 exceptions are swallowed by the inner ``add_memory`` (already
  unit-tested in test_memory.py); this test verifies the *call shape*.

Uses real DB rows (Conversation + Message) created in-test, rolled back
on teardown. ``add_memory`` itself is monkeypatched so the test doesn't
need Pellet credits.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models.agent import Agent, AgentStatus
from app.models.conversation import (
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
)
from app.models.user import Organization


@pytest_asyncio.fixture
async def db_engine(monkeypatch):
    """Per-test engine, also installed as the app-level ``async_session_factory``.

    The helper under test (``_post_call_memory_write``) opens its own session
    via ``async_session_factory`` from ``app.database``. If we let it use the
    module-global engine, that engine's pool outlives the test event loop
    and the next test's loop closure trips an asyncpg cancellation race
    (``RuntimeError: Event loop is closed``). Patching the factory to point
    at our function-scoped engine ensures connections are owned by the same
    loop they were created on, and disposed before the loop closes.
    """
    if not settings.DATABASE_URL:
        pytest.skip("DATABASE_URL not configured")
    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    # Redirect app.database.async_session_factory to the test engine.
    test_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.database.async_session_factory", test_factory)

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def conversation_with_messages(db_engine):
    """Create a Conversation with a known mix of message roles."""
    Session = async_sessionmaker(db_engine, expire_on_commit=False)
    async with Session() as s:
        org = Organization(id=uuid.uuid4(), name=f"t-{uuid.uuid4().hex[:6]}")
        agent = Agent(
            id=uuid.uuid4(), org_id=org.id,
            name=f"a-{uuid.uuid4().hex[:6]}",
            status=AgentStatus.PUBLISHED,
        )
        conv = Conversation(
            id=uuid.uuid4(), agent_id=agent.id,
            status=ConversationStatus.COMPLETED,
        )
        s.add_all([org, agent, conv])
        await s.flush()

        # Mixed roles in chronological order (created_at strictly increasing
        # so the ORDER BY in the helper is deterministic).
        from datetime import datetime, timedelta, timezone
        base = datetime.now(timezone.utc)
        msgs = [
            Message(conversation_id=conv.id, role=MessageRole.USER,
                    content="Hi, I'm Aarti"),
            Message(conversation_id=conv.id, role=MessageRole.ASSISTANT,
                    content="Hello Aarti"),
            Message(conversation_id=conv.id, role=MessageRole.SYSTEM,
                    content="[State transition] greeting -> info"),  # filter out
            Message(conversation_id=conv.id, role=MessageRole.USER,
                    content="What's my balance?"),
            Message(conversation_id=conv.id, role=MessageRole.TOOL,
                    content='{"balance": 5400}'),  # filter out
            Message(conversation_id=conv.id, role=MessageRole.ASSISTANT,
                    content="Your balance is Rs 5400"),
        ]
        for i, m in enumerate(msgs):
            # set created_at explicitly so ordering is deterministic
            m.created_at = base + timedelta(seconds=i)
        s.add_all(msgs)
        await s.commit()

    yield conv.id, agent.id

    # Teardown
    async with Session() as s:
        await s.execute(delete(Conversation).where(Conversation.id == conv.id))
        await s.execute(delete(Agent).where(Agent.id == agent.id))
        await s.execute(delete(Organization).where(Organization.id == org.id))
        await s.commit()


@pytest.mark.asyncio
async def test_filters_to_user_and_assistant_only(
    conversation_with_messages, monkeypatch,
):
    conv_id, agent_id = conversation_with_messages
    end_user_id = uuid.uuid4()

    captured_messages = []

    async def fake_add(eu_id, ag_id, messages):
        captured_messages.extend(messages)

    # Patch BEFORE importing _post_call_memory_write; the helper imports
    # add_memory at the top of webhooks.py, so we patch through the
    # webhooks namespace.
    from app.api.v1 import webhooks
    monkeypatch.setattr(webhooks, "add_memory", AsyncMock(side_effect=fake_add))

    await webhooks._post_call_memory_write(conv_id, end_user_id, agent_id)

    # SYSTEM + TOOL messages are filtered out
    roles = [m["role"] for m in captured_messages]
    assert all(r in ("user", "assistant") for r in roles), roles
    assert "system" not in roles
    assert "tool" not in roles

    # USER + ASSISTANT messages preserved in chronological order
    contents = [m["content"] for m in captured_messages]
    assert contents == [
        "Hi, I'm Aarti",
        "Hello Aarti",
        "What's my balance?",
        "Your balance is Rs 5400",
    ]


@pytest_asyncio.fixture
async def empty_conversation(db_engine):
    """Conversation with NO messages — used to verify the no-op path."""
    Session = async_sessionmaker(db_engine, expire_on_commit=False)
    async with Session() as s:
        org = Organization(id=uuid.uuid4(), name=f"t-{uuid.uuid4().hex[:6]}")
        agent = Agent(
            id=uuid.uuid4(), org_id=org.id,
            name=f"a-{uuid.uuid4().hex[:6]}",
            status=AgentStatus.PUBLISHED,
        )
        conv = Conversation(
            id=uuid.uuid4(), agent_id=agent.id,
            status=ConversationStatus.COMPLETED,
        )
        s.add_all([org, agent, conv])
        await s.commit()

    yield conv.id, agent.id

    async with Session() as s:
        await s.execute(delete(Conversation).where(Conversation.id == conv.id))
        await s.execute(delete(Agent).where(Agent.id == agent.id))
        await s.execute(delete(Organization).where(Organization.id == org.id))
        await s.commit()


@pytest.mark.asyncio
async def test_empty_conversation_skips_mem0_call(empty_conversation, monkeypatch):
    """A Conversation with no messages results in NO call to mem0.add."""
    conv_id, agent_id = empty_conversation

    from app.api.v1 import webhooks
    mock_add = AsyncMock()
    monkeypatch.setattr(webhooks, "add_memory", mock_add)

    await webhooks._post_call_memory_write(conv_id, uuid.uuid4(), agent_id)

    mock_add.assert_not_called()


@pytest.mark.asyncio
async def test_calls_add_memory_with_correct_uuids(
    conversation_with_messages, monkeypatch,
):
    """add_memory receives the exact (end_user_id, agent_id) it was passed."""
    conv_id, agent_id = conversation_with_messages
    end_user_id = uuid.uuid4()

    from app.api.v1 import webhooks
    mock_add = AsyncMock()
    monkeypatch.setattr(webhooks, "add_memory", mock_add)

    await webhooks._post_call_memory_write(conv_id, end_user_id, agent_id)

    mock_add.assert_called_once()
    call_args = mock_add.call_args
    # Helper signature: add_memory(end_user_id, agent_id, messages)
    assert call_args.args[0] == end_user_id
    assert call_args.args[1] == agent_id
