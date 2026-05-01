"""Integration tests for ``EndUserService.get_or_create_by_caller``.

These run against the dev Postgres (alembic-migrated) and validate the
race-safe upsert behavior end-to-end. Without DB-bound tests we'd be
trusting that ``ON CONFLICT DO UPDATE`` keys correctly off the partial
unique indexes — which silently fails if the index is missing or
``index_where`` doesn't match the predicate.

Skipped automatically when DATABASE_URL is unconfigured (see ``conftest``).
"""

from __future__ import annotations

import asyncio

import pytest

from app.models.end_user import EndUser
from app.services.end_user_service import EndUserService


# ---------------------------------------------------------------------------
# Phone path — parseable phone numbers go to phone_number column
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_phone_path_normalizes_and_stores_e164(db_session, test_agent):
    svc = EndUserService(db_session)
    eu = await svc.get_or_create_by_caller(test_agent.id, "9876543210", name="Aarti")
    assert eu is not None
    assert eu.phone_number == "+919876543210"
    assert eu.external_id is None
    assert eu.name == "Aarti"


@pytest.mark.asyncio
async def test_phone_path_idempotent_same_caller(db_session, test_agent):
    """Two calls with the same caller produce ONE EndUser row."""
    svc = EndUserService(db_session)
    eu1 = await svc.get_or_create_by_caller(test_agent.id, "9876543210", name="Aarti")
    eu2 = await svc.get_or_create_by_caller(test_agent.id, "+919876543210")
    assert eu2.id == eu1.id


@pytest.mark.asyncio
async def test_phone_path_preserves_existing_name(db_session, test_agent):
    """A second call without a name doesn't blank out the stored name."""
    svc = EndUserService(db_session)
    await svc.get_or_create_by_caller(test_agent.id, "9876543210", name="Aarti")
    eu2 = await svc.get_or_create_by_caller(test_agent.id, "9876543210", name=None)
    assert eu2.name == "Aarti"


@pytest.mark.asyncio
async def test_phone_path_overwrites_with_new_name(db_session, test_agent):
    """A second call WITH a new name updates the row.

    ``COALESCE(EXCLUDED.name, end_users.name)`` keeps EXCLUDED's value when
    it's non-null; the stored row's name only "wins" when EXCLUDED is null.
    """
    svc = EndUserService(db_session)
    await svc.get_or_create_by_caller(test_agent.id, "9876543210", name="Aarti")
    eu2 = await svc.get_or_create_by_caller(test_agent.id, "9876543210", name="Aarti Sharma")
    assert eu2.name == "Aarti Sharma"


# ---------------------------------------------------------------------------
# External ID path — non-phone identifiers go to external_id column
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sip_uri_routes_to_external_id(db_session, test_agent):
    sip = "sip:agentstudio.test@phone.plivo.com"
    svc = EndUserService(db_session)
    eu = await svc.get_or_create_by_caller(test_agent.id, sip, name="SIP-Tester")
    assert eu is not None
    assert eu.phone_number is None
    assert eu.external_id == sip


@pytest.mark.asyncio
async def test_chatbot_user_id_routes_to_external_id(db_session, test_agent):
    """Chatbot user_ids are typically opaque strings — should land in external_id."""
    svc = EndUserService(db_session)
    eu = await svc.get_or_create_by_caller(test_agent.id, "user-abc-12345")
    assert eu is not None
    assert eu.phone_number is None
    assert eu.external_id == "user-abc-12345"


@pytest.mark.asyncio
async def test_external_id_path_idempotent(db_session, test_agent):
    svc = EndUserService(db_session)
    eu1 = await svc.get_or_create_by_caller(test_agent.id, "user-abc")
    eu2 = await svc.get_or_create_by_caller(test_agent.id, "user-abc")
    assert eu2.id == eu1.id


# ---------------------------------------------------------------------------
# Anonymous (None / empty) — returns None, no row created
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [None, "", "   "])
async def test_anonymous_returns_none(db_session, test_agent, raw):
    svc = EndUserService(db_session)
    eu = await svc.get_or_create_by_caller(test_agent.id, raw)
    assert eu is None


# ---------------------------------------------------------------------------
# Per-agent scope: same phone, different agent → different EndUser
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_phone_different_agents_creates_distinct_rows(
    db_session, test_agent,
):
    """Identity is per-agent. Caller calling Agent A and Agent B yields two rows.

    Cross-agent unification is intentionally out of scope (different
    tenancy / context); the partial unique index includes agent_id so
    the same E.164 against a different agent_id doesn't conflict.
    """
    from app.models.agent import Agent, AgentStatus
    import uuid

    agent2 = Agent(
        id=uuid.uuid4(), org_id=test_agent.org_id,
        name=f"test-agent-2-{uuid.uuid4().hex[:8]}",
        status=AgentStatus.PUBLISHED,
    )
    db_session.add(agent2)
    await db_session.commit()

    try:
        svc = EndUserService(db_session)
        eu1 = await svc.get_or_create_by_caller(test_agent.id, "9876543210")
        eu2 = await svc.get_or_create_by_caller(agent2.id, "9876543210")
        assert eu1.id != eu2.id
        assert eu1.phone_number == eu2.phone_number == "+919876543210"
    finally:
        from sqlalchemy import delete
        await db_session.execute(delete(Agent).where(Agent.id == agent2.id))
        await db_session.commit()


# ---------------------------------------------------------------------------
# Concurrent upsert race — two coroutines hitting same key, one row out
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_upserts_produce_one_row(db_session, test_agent):
    """Race-safety: two simultaneous get_or_create_by_caller for same caller.

    The partial unique index + ON CONFLICT DO UPDATE means whichever coroutine
    inserts second sees a conflict and updates the existing row. End state:
    exactly one row, both coroutines see the same UUID.

    Each coroutine gets its own session — sharing one session would
    serialize them via SQLAlchemy's session lock and not test the actual
    concurrent-write race.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.config import settings

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def upsert(name: str):
        async with Session() as s:
            return await EndUserService(s).get_or_create_by_caller(
                test_agent.id, "9876543210", name=name,
            )

    try:
        eu1, eu2 = await asyncio.gather(upsert("Aarti"), upsert("Aarti Sharma"))
        assert eu1.id == eu2.id
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# increment_conversation_count — atomic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_increment_conversation_count_is_atomic(db_session, test_agent):
    svc = EndUserService(db_session)
    eu = await svc.get_or_create_by_caller(test_agent.id, "9876543210")
    assert eu.total_conversations == 0

    await svc.increment_conversation_count(eu.id)
    await svc.increment_conversation_count(eu.id)
    await svc.increment_conversation_count(eu.id)

    await db_session.refresh(eu)
    assert eu.total_conversations == 3
