"""Tests for the WhatsApp/chatbot idle-sweep Celery task.

Mocks ``_post_call_memory_write`` so we test the SWEEP'S logic — the
downstream function is covered separately. Real DB rows used because
the candidate query involves the partial index + ``last_message_at``
predicates which mocks can't represent.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models.agent import Agent, AgentStatus
from app.models.conversation import Conversation, ConversationStatus
from app.models.end_user import EndUser
from app.models.user import Organization


@pytest_asyncio.fixture
async def db_engine(monkeypatch):
    if not settings.DATABASE_URL:
        pytest.skip("DATABASE_URL not configured")
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    test_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.database.async_session_factory", test_factory)
    yield engine
    await engine.dispose()


async def _create_conversations(engine, fixtures):
    """fixtures: list of dicts {idle_min, written, attempts, with_end_user}."""
    Session = async_sessionmaker(engine, expire_on_commit=False)
    created = []
    async with Session() as s:
        org = Organization(id=uuid.uuid4(), name=f"t-{uuid.uuid4().hex[:6]}")
        agent = Agent(
            id=uuid.uuid4(), org_id=org.id,
            name=f"a-{uuid.uuid4().hex[:6]}",
            status=AgentStatus.PUBLISHED,
        )
        s.add_all([org, agent])
        await s.flush()

        now = datetime.now(timezone.utc)
        for fx in fixtures:
            eu = None
            if fx.get("with_end_user", True):
                eu = EndUser(
                    id=uuid.uuid4(), agent_id=agent.id,
                    phone_number=f"+91{uuid.uuid4().int % 10**10:010d}",
                )
                s.add(eu)
            conv = Conversation(
                id=uuid.uuid4(), agent_id=agent.id,
                status=ConversationStatus.ACTIVE,
                end_user_id=eu.id if eu else None,
                last_message_at=now - timedelta(minutes=fx["idle_min"]),
                memory_written_at=now if fx.get("written") else None,
                memory_extraction_attempts=fx.get("attempts", 0),
            )
            s.add(conv)
            created.append(conv)
        await s.commit()
        return org.id, agent.id, [c.id for c in created], [
            c.end_user_id for c in created
        ]


async def _cleanup(engine, org_id, agent_id, conv_ids):
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        for cid in conv_ids:
            await s.execute(delete(Conversation).where(Conversation.id == cid))
        await s.execute(delete(EndUser).where(EndUser.agent_id == agent_id))
        await s.execute(delete(Agent).where(Agent.id == agent_id))
        await s.execute(delete(Organization).where(Organization.id == org_id))
        await s.commit()


@pytest.mark.asyncio
async def test_picks_only_idle_unwritten_with_end_user(db_engine, monkeypatch):
    """Sweep picks the eligible fixture; excludes the ineligible ones.

    The dev DB has historical conversations that may match the predicate
    too. We assert by SET INCLUSION on our test conversation IDs — the
    eligible one MUST be picked, the ineligible ones MUST NOT be —
    without bounding the global count.
    """
    threshold = settings.MEMORY_IDLE_THRESHOLD_MINUTES
    org_id, agent_id, conv_ids, end_user_ids = await _create_conversations(
        db_engine,
        fixtures=[
            # 0: eligible — idle past threshold, unwritten, has end_user
            {"idle_min": threshold + 5},
            # 1: too fresh — within threshold
            {"idle_min": max(0, threshold - 2)},
            # 2: already written — excluded
            {"idle_min": threshold + 5, "written": True},
            # 3: anonymous (no end_user) — excluded
            {"idle_min": threshold + 5, "with_end_user": False},
            # 4: cap reached — excluded
            {"idle_min": threshold + 5,
             "attempts": settings.MEMORY_MAX_EXTRACTION_ATTEMPTS},
        ],
    )
    try:
        picked: dict[uuid.UUID, dict] = {}

        async def fake_post_call(conv_id, end_user_id, agent_id_arg, *,
                                 close_conversation=False):
            picked[conv_id] = {
                "end_user_id": end_user_id,
                "close_conversation": close_conversation,
            }

        from app.workers import memory_tasks
        from app.api.v1 import webhooks
        monkeypatch.setattr(webhooks, "_post_call_memory_write",
                            AsyncMock(side_effect=fake_post_call))

        await memory_tasks._extract_idle_conversations_async()

        # Inclusion: eligible row MUST be picked.
        assert conv_ids[0] in picked, (
            f"Eligible fixture not picked. picked={list(picked.keys())}"
        )
        # close_conversation=True is the sweep's signature.
        assert picked[conv_ids[0]]["close_conversation"] is True
        # Exclusion: ineligible rows MUST NOT be picked.
        for excluded_idx in (1, 2, 3, 4):
            assert conv_ids[excluded_idx] not in picked, (
                f"Ineligible fixture conv_ids[{excluded_idx}] was picked"
            )
    finally:
        await _cleanup(db_engine, org_id, agent_id, conv_ids)


@pytest.mark.asyncio
async def test_attempts_cap_excludes_from_sweep(db_engine, monkeypatch):
    """A conversation at attempts == MAX is invisible to the sweep."""
    threshold = settings.MEMORY_IDLE_THRESHOLD_MINUTES
    org_id, agent_id, conv_ids, _ = await _create_conversations(
        db_engine,
        fixtures=[
            {"idle_min": threshold + 10,
             "attempts": settings.MEMORY_MAX_EXTRACTION_ATTEMPTS},
        ],
    )
    try:
        picked = set()

        async def fake_post_call(conv_id, *a, **kw):
            picked.add(conv_id)

        from app.workers import memory_tasks
        from app.api.v1 import webhooks
        monkeypatch.setattr(webhooks, "_post_call_memory_write",
                            AsyncMock(side_effect=fake_post_call))

        await memory_tasks._extract_idle_conversations_async()

        # Inclusion check — our capped row is NOT picked.
        assert conv_ids[0] not in picked, (
            f"Capped conversation was picked despite attempts={settings.MEMORY_MAX_EXTRACTION_ATTEMPTS}"
        )
    finally:
        await _cleanup(db_engine, org_id, agent_id, conv_ids)


@pytest.mark.asyncio
async def test_fresh_conversations_excluded(db_engine, monkeypatch):
    """Conversations within the idle threshold are NOT picked."""
    threshold = settings.MEMORY_IDLE_THRESHOLD_MINUTES
    org_id, agent_id, conv_ids, _ = await _create_conversations(
        db_engine,
        fixtures=[
            # Just under the cutoff (cap at 0 if threshold is very small).
            {"idle_min": max(0, threshold - 1)},
        ],
    )
    try:
        picked = set()

        async def fake_post_call(conv_id, *a, **kw):
            picked.add(conv_id)

        from app.workers import memory_tasks
        from app.api.v1 import webhooks
        monkeypatch.setattr(webhooks, "_post_call_memory_write",
                            AsyncMock(side_effect=fake_post_call))

        await memory_tasks._extract_idle_conversations_async()

        assert conv_ids[0] not in picked, (
            "Fresh conversation was picked despite being within the threshold"
        )
    finally:
        await _cleanup(db_engine, org_id, agent_id, conv_ids)
