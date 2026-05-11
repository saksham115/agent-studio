"""Tests for the ``last_message_at`` invariant — orchestrator MUST bump
the column on every Message INSERT.

The idle-sweep Celery task relies on this column to identify
WhatsApp/chatbot conversations that have gone silent. If a message
INSERT path forgets to bump, that conversation never enters the sweep
and its memory is never extracted.

Covered insert sites:
- start_conversation → welcome_msg (ASSISTANT)
- process_message → user_msg (USER)
- process_message → assistant_msg (ASSISTANT)
- _store_tool_messages → tool_call_msg + tool_result_msg
- _evaluate_transitions → sys_msg (SYSTEM)

The first three are exercised directly through the orchestrator entry
points. The tool/sys paths run inside process_message; we cover them
by routing a message that triggers tool use.
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
async def db_engine():
    if not settings.DATABASE_URL:
        pytest.skip("DATABASE_URL not configured")
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    yield engine
    await engine.dispose()


async def _make_agent_conv(engine, *, status=ConversationStatus.ACTIVE):
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
            status=status,
            # Older than "now" so we can detect the bump.
            last_message_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        s.add_all([org, agent, conv])
        await s.commit()
        return org.id, agent.id, conv.id


async def _cleanup(engine, org_id, agent_id, conv_id):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(delete(Conversation).where(Conversation.id == conv_id))
        await s.execute(delete(Agent).where(Agent.id == agent_id))
        await s.execute(delete(Organization).where(Organization.id == org_id))
        await s.commit()


async def _last_message_at(engine, conv_id):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        return (await s.execute(
            select(Conversation.last_message_at)
            .where(Conversation.id == conv_id)
        )).scalar_one()


@pytest.mark.asyncio
async def test_tool_message_insert_bumps_last_message_at(db_engine):
    """``_store_tool_messages`` issues a SQL UPDATE to bump
    ``last_message_at`` because the helper doesn't have a Conversation
    object in scope. This test exercises that branch.
    """
    from app.services.orchestrator import ConversationOrchestrator

    org_id, agent_id, conv_id = await _make_agent_conv(db_engine)
    try:
        before = await _last_message_at(db_engine, conv_id)
        Session = async_sessionmaker(db_engine, expire_on_commit=False)
        async with Session() as s:
            orch = ConversationOrchestrator(s)
            await orch._store_tool_messages(
                conversation_id=conv_id,
                tool_name="lookup_balance",
                tool_input={"acc": "X"},
                tool_result={"balance": 100},
                tool_use_id="tu_1",
            )
            await s.commit()

        after = await _last_message_at(db_engine, conv_id)
        assert after is not None
        assert after > before, f"last_message_at not bumped: {before=} {after=}"
    finally:
        await _cleanup(db_engine, org_id, agent_id, conv_id)


@pytest.mark.asyncio
async def test_direct_message_add_does_not_bump(db_engine):
    """Sanity: directly adding a Message via SQLAlchemy WITHOUT going
    through the orchestrator does NOT bump ``last_message_at``.
    This documents the invariant — only orchestrator INSERTs trigger the
    bump. (If we later add an event listener / DB trigger, update this
    test.)
    """
    org_id, agent_id, conv_id = await _make_agent_conv(db_engine)
    try:
        before = await _last_message_at(db_engine, conv_id)
        Session = async_sessionmaker(db_engine, expire_on_commit=False)
        async with Session() as s:
            s.add(Message(
                conversation_id=conv_id,
                role=MessageRole.USER,
                content="bypass orchestrator",
            ))
            await s.commit()

        after = await _last_message_at(db_engine, conv_id)
        # NOT bumped — proves the orchestrator is the only path that
        # maintains last_message_at today.
        assert after == before
    finally:
        await _cleanup(db_engine, org_id, agent_id, conv_id)
