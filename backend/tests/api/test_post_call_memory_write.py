"""Tests for ``webhooks._post_call_memory_write`` — the hardened BackgroundTask helper.

Per v5 plan, this function is the load-bearing memory-write entrypoint for
voice / chatbot / Celery sweep. It must be:

- Idempotent: a second call for the same conversation short-circuits at the
  ``FOR UPDATE`` guard once memory_written_at is set.
- Success-conditional: only marks memory_written_at when add_memory returns
  True. Failure increments memory_extraction_attempts.
- Cap-aware: short-circuits when attempts >= MEMORY_MAX_EXTRACTION_ATTEMPTS.
- Atomic-close: when close_conversation=True, writes
  memory_written_at + status=COMPLETED + ended_at in ONE transaction.

Mocks ``add_memory`` at the public boundary so tests don't depend on Agno
internals.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
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
    """Per-test engine, also installed as ``app.database.async_session_factory``."""
    if not settings.DATABASE_URL:
        pytest.skip("DATABASE_URL not configured")
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    test_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.database.async_session_factory", test_factory)
    yield engine
    await engine.dispose()


async def _make_conversation(engine, *, with_messages=True, status=None,
                              memory_written_at=None, attempts=0):
    """Build a Conversation + Agent + Org + optional Messages. Returns ids."""
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        org = Organization(id=uuid.uuid4(), name=f"t-{uuid.uuid4().hex[:6]}")
        agent = Agent(
            id=uuid.uuid4(), org_id=org.id,
            name=f"a-{uuid.uuid4().hex[:6]}",
            status=AgentStatus.PUBLISHED,
        )
        conv = Conversation(
            id=uuid.uuid4(), agent_id=agent.id,
            status=status or ConversationStatus.COMPLETED,
            memory_written_at=memory_written_at,
            memory_extraction_attempts=attempts,
        )
        s.add_all([org, agent, conv])
        await s.flush()
        if with_messages:
            base = datetime.now(timezone.utc)
            msgs = [
                Message(conversation_id=conv.id, role=MessageRole.USER,
                        content="Hi, I'm Aarti"),
                Message(conversation_id=conv.id, role=MessageRole.ASSISTANT,
                        content="Hello Aarti"),
            ]
            for i, m in enumerate(msgs):
                m.created_at = base + timedelta(seconds=i)
            s.add_all(msgs)
        await s.commit()
        return conv.id, agent.id, org.id


async def _cleanup(engine, conv_id, agent_id, org_id):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(delete(Conversation).where(Conversation.id == conv_id))
        await s.execute(delete(Agent).where(Agent.id == agent_id))
        await s.execute(delete(Organization).where(Organization.id == org_id))
        await s.commit()


async def _conversation_state(engine, conv_id):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        row = (await s.execute(
            select(Conversation).where(Conversation.id == conv_id)
        )).scalar_one()
        return {
            "memory_written_at": row.memory_written_at,
            "memory_extraction_attempts": row.memory_extraction_attempts,
            "status": row.status,
            "ended_at": row.ended_at,
        }


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_success_path_sets_memory_written_at(db_engine, monkeypatch):
    conv_id, agent_id, org_id = await _make_conversation(db_engine)
    try:
        from app.api.v1 import webhooks
        monkeypatch.setattr(webhooks, "add_memory", AsyncMock(return_value=True))

        await webhooks._post_call_memory_write(conv_id, uuid.uuid4(), agent_id)

        state = await _conversation_state(db_engine, conv_id)
        assert state["memory_written_at"] is not None
        assert state["memory_extraction_attempts"] == 0
    finally:
        await _cleanup(db_engine, conv_id, agent_id, org_id)


# ---------------------------------------------------------------------------
# Failure path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failure_increments_attempts_leaves_written_at_null(
    db_engine, monkeypatch,
):
    conv_id, agent_id, org_id = await _make_conversation(db_engine)
    try:
        from app.api.v1 import webhooks
        monkeypatch.setattr(webhooks, "add_memory", AsyncMock(return_value=False))

        await webhooks._post_call_memory_write(conv_id, uuid.uuid4(), agent_id)

        state = await _conversation_state(db_engine, conv_id)
        assert state["memory_written_at"] is None
        assert state["memory_extraction_attempts"] == 1
    finally:
        await _cleanup(db_engine, conv_id, agent_id, org_id)


# ---------------------------------------------------------------------------
# Idempotency — already-written short-circuits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idempotent_when_already_written(db_engine, monkeypatch):
    written_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    conv_id, agent_id, org_id = await _make_conversation(
        db_engine, memory_written_at=written_at,
    )
    try:
        from app.api.v1 import webhooks
        mock_add = AsyncMock(return_value=True)
        monkeypatch.setattr(webhooks, "add_memory", mock_add)

        await webhooks._post_call_memory_write(conv_id, uuid.uuid4(), agent_id)

        # Short-circuited at the guard — add_memory NOT called.
        mock_add.assert_not_awaited()
        state = await _conversation_state(db_engine, conv_id)
        # written_at preserved (down to second since DB stores microsecond
        # precision; compare loosely).
        assert state["memory_written_at"] is not None
        assert abs(
            (state["memory_written_at"] - written_at).total_seconds()
        ) < 1
    finally:
        await _cleanup(db_engine, conv_id, agent_id, org_id)


# ---------------------------------------------------------------------------
# Cap — attempts >= MAX short-circuits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_short_circuits_when_attempts_cap_reached(db_engine, monkeypatch):
    conv_id, agent_id, org_id = await _make_conversation(
        db_engine, attempts=settings.MEMORY_MAX_EXTRACTION_ATTEMPTS,
    )
    try:
        from app.api.v1 import webhooks
        mock_add = AsyncMock(return_value=True)
        monkeypatch.setattr(webhooks, "add_memory", mock_add)

        await webhooks._post_call_memory_write(conv_id, uuid.uuid4(), agent_id)

        mock_add.assert_not_awaited()
        state = await _conversation_state(db_engine, conv_id)
        assert state["memory_written_at"] is None
        assert state["memory_extraction_attempts"] == settings.MEMORY_MAX_EXTRACTION_ATTEMPTS
    finally:
        await _cleanup(db_engine, conv_id, agent_id, org_id)


# ---------------------------------------------------------------------------
# Atomic close — close_conversation=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_conversation_sets_completed_and_ended_at(db_engine, monkeypatch):
    conv_id, agent_id, org_id = await _make_conversation(
        db_engine, status=ConversationStatus.ACTIVE,
    )
    try:
        from app.api.v1 import webhooks
        monkeypatch.setattr(webhooks, "add_memory", AsyncMock(return_value=True))

        await webhooks._post_call_memory_write(
            conv_id, uuid.uuid4(), agent_id, close_conversation=True,
        )

        state = await _conversation_state(db_engine, conv_id)
        assert state["memory_written_at"] is not None
        assert state["status"] == ConversationStatus.COMPLETED
        assert state["ended_at"] is not None
    finally:
        await _cleanup(db_engine, conv_id, agent_id, org_id)


@pytest.mark.asyncio
async def test_close_false_leaves_status_unchanged(db_engine, monkeypatch):
    conv_id, agent_id, org_id = await _make_conversation(
        db_engine, status=ConversationStatus.ACTIVE,
    )
    try:
        from app.api.v1 import webhooks
        monkeypatch.setattr(webhooks, "add_memory", AsyncMock(return_value=True))

        await webhooks._post_call_memory_write(
            conv_id, uuid.uuid4(), agent_id, close_conversation=False,
        )

        state = await _conversation_state(db_engine, conv_id)
        # memory_written_at set on success.
        assert state["memory_written_at"] is not None
        # status NOT modified (voice/chatbot close via their own paths).
        assert state["status"] == ConversationStatus.ACTIVE
        assert state["ended_at"] is None
    finally:
        await _cleanup(db_engine, conv_id, agent_id, org_id)


# ---------------------------------------------------------------------------
# Empty conversation — no add_memory call, no state change
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_conversation_no_add_memory(db_engine, monkeypatch):
    conv_id, agent_id, org_id = await _make_conversation(
        db_engine, with_messages=False,
    )
    try:
        from app.api.v1 import webhooks
        mock_add = AsyncMock(return_value=True)
        monkeypatch.setattr(webhooks, "add_memory", mock_add)

        await webhooks._post_call_memory_write(conv_id, uuid.uuid4(), agent_id)

        mock_add.assert_not_awaited()
        state = await _conversation_state(db_engine, conv_id)
        # No state change.
        assert state["memory_written_at"] is None
        assert state["memory_extraction_attempts"] == 0
    finally:
        await _cleanup(db_engine, conv_id, agent_id, org_id)


# ---------------------------------------------------------------------------
# Message filtering — SYSTEM/TOOL excluded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filters_to_user_and_assistant_only(db_engine, monkeypatch):
    """Mixed-role conversation — only USER + ASSISTANT messages get forwarded."""
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
        base = datetime.now(timezone.utc)
        msgs = [
            Message(conversation_id=conv.id, role=MessageRole.USER,
                    content="Hi"),
            Message(conversation_id=conv.id, role=MessageRole.ASSISTANT,
                    content="Hello"),
            Message(conversation_id=conv.id, role=MessageRole.SYSTEM,
                    content="[State transition]"),
            Message(conversation_id=conv.id, role=MessageRole.TOOL,
                    content='{"balance": 1}'),
        ]
        for i, m in enumerate(msgs):
            m.created_at = base + timedelta(seconds=i)
        s.add_all(msgs)
        await s.commit()
    conv_id, agent_id, org_id = conv.id, agent.id, org.id

    try:
        captured = []

        async def fake_add(eu, ag, messages):
            captured.extend(messages)
            return True

        from app.api.v1 import webhooks
        monkeypatch.setattr(webhooks, "add_memory", AsyncMock(side_effect=fake_add))

        await webhooks._post_call_memory_write(conv_id, uuid.uuid4(), agent_id)

        roles = [m["role"] for m in captured]
        assert roles == ["user", "assistant"]
    finally:
        await _cleanup(db_engine, conv_id, agent_id, org_id)
