"""Tests for chatbot ``end_session`` scheduling the memory-write BackgroundTask.

We verify the trigger contract — when ``end_session`` returns, the task is
queued with the right args. The downstream behavior of
``_post_call_memory_write`` is covered by ``test_post_call_memory_write.py``.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from fastapi import BackgroundTasks
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models.agent import Agent, AgentStatus
from app.models.conversation import Conversation, ConversationStatus
from app.models.end_user import EndUser
from app.models.user import Organization


@pytest_asyncio.fixture
async def db_engine():
    if not settings.DATABASE_URL:
        pytest.skip("DATABASE_URL not configured")
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    yield engine
    await engine.dispose()


async def _setup_session(engine, *, with_end_user=True):
    """Create the minimum (Org, Agent, optional EndUser, Conversation) for
    the test. ChatbotApiKey is NOT created — the test invokes end_session
    directly, bypassing the validate_api_key FastAPI dependency, so the
    key row isn't on the code path.
    """
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        org = Organization(id=uuid.uuid4(), name=f"t-{uuid.uuid4().hex[:6]}")
        agent = Agent(
            id=uuid.uuid4(), org_id=org.id,
            name=f"a-{uuid.uuid4().hex[:6]}",
            status=AgentStatus.PUBLISHED,
        )
        s.add_all([org, agent])
        # Flush so the agents row exists before EndUser's FK fires. SQLAlchemy
        # doesn't auto-order these two without a defined relationship.
        await s.flush()

        end_user = None
        if with_end_user:
            end_user = EndUser(
                id=uuid.uuid4(), agent_id=agent.id,
                phone_number=f"+91{uuid.uuid4().int % 10**10:010d}",
            )
            s.add(end_user)
            await s.flush()
        conv = Conversation(
            id=uuid.uuid4(), agent_id=agent.id,
            status=ConversationStatus.ACTIVE,
            end_user_id=end_user.id if end_user else None,
        )
        s.add(conv)
        await s.commit()
        return {
            "conv_id": conv.id,
            "agent_id": agent.id,
            "org_id": org.id,
            "end_user_id": end_user.id if end_user else None,
        }


async def _cleanup(engine, ids):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(delete(Conversation).where(Conversation.id == ids["conv_id"]))
        if ids["end_user_id"]:
            await s.execute(delete(EndUser).where(EndUser.id == ids["end_user_id"]))
        await s.execute(delete(Agent).where(Agent.id == ids["agent_id"]))
        await s.execute(delete(Organization).where(Organization.id == ids["org_id"]))
        await s.commit()


@pytest.mark.asyncio
async def test_end_session_schedules_memory_write_when_end_user_set(
    db_engine, monkeypatch,
):
    """end_session with end_user_id → schedules _post_call_memory_write."""
    ids = await _setup_session(db_engine, with_end_user=True)
    try:
        from app.api.v1 import chatbot
        Session = async_sessionmaker(db_engine, expire_on_commit=False)
        async with Session() as s:
            bg = MagicMock(spec=BackgroundTasks)
            await chatbot.end_session(
                agent_id=ids["agent_id"],
                session_id=ids["conv_id"],
                background_tasks=bg,
                db=s,
                agent=MagicMock(id=ids["agent_id"]),
            )
        # BackgroundTask was scheduled exactly once.
        bg.add_task.assert_called_once()
        # First arg is the task function.
        from app.api.v1.webhooks import _post_call_memory_write
        assert bg.add_task.call_args.args[0] is _post_call_memory_write
        # Positional args: (conv_id, end_user_id, agent_id).
        assert bg.add_task.call_args.args[1] == ids["conv_id"]
        assert bg.add_task.call_args.args[2] == ids["end_user_id"]
        assert bg.add_task.call_args.args[3] == ids["agent_id"]
    finally:
        await _cleanup(db_engine, ids)


@pytest.mark.asyncio
async def test_end_session_skips_memory_write_when_no_end_user(
    db_engine, monkeypatch,
):
    """Anonymous chatbot session (end_user_id NULL) → no task scheduled."""
    ids = await _setup_session(db_engine, with_end_user=False)
    try:
        from app.api.v1 import chatbot
        Session = async_sessionmaker(db_engine, expire_on_commit=False)
        async with Session() as s:
            bg = MagicMock(spec=BackgroundTasks)
            await chatbot.end_session(
                agent_id=ids["agent_id"],
                session_id=ids["conv_id"],
                background_tasks=bg,
                db=s,
                agent=MagicMock(id=ids["agent_id"]),
            )
        bg.add_task.assert_not_called()
    finally:
        await _cleanup(db_engine, ids)
