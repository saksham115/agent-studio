"""Service-test-specific fixtures."""

from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture(autouse=True)
def _reset_agno_singletons():
    """Clear ``memory.py``'s per-loop singleton between tests.

    The Agno wrapper stores ``(db, mm)`` as an attribute on the running
    event loop via ``setattr(loop, _LOOP_SLOT, ...)``. pytest-asyncio
    reuses a single event loop across tests by default, so without
    cleanup a previous test's monkey-patched components leak into the
    next. We can't ``asyncio.get_running_loop()`` from a sync fixture, so
    we instead delete the slot from any loop attached to ``asyncio.events``
    on teardown — cheap, idempotent, harmless when no loop exists yet.
    """
    yield
    import sys
    mod = sys.modules.get("app.services.memory")
    if mod is None:
        return
    slot = getattr(mod, "_LOOP_SLOT", None)
    if slot is None:
        return
    # Best-effort: walk both the running loop (if any) and the policy's
    # default loop. asyncio.get_event_loop() in 3.10 may auto-create.
    for getter in (asyncio.get_event_loop_policy().get_event_loop,):
        try:
            loop = getter()
            if hasattr(loop, slot):
                delattr(loop, slot)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# DB fixtures for tests that need real SQLAlchemy + Postgres
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Per-test AsyncSession against the dev Postgres."""
    from app.config import settings

    if not settings.DATABASE_URL:
        pytest.skip("DATABASE_URL not configured; skipping DB-bound tests")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_agent(db_session):
    """A throwaway published Agent the EndUser FK can attach to."""
    from app.models.agent import Agent, AgentStatus
    from app.models.user import Organization

    org = Organization(
        id=uuid.uuid4(),
        name=f"test-org-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(org)

    agent = Agent(
        id=uuid.uuid4(),
        org_id=org.id,
        name=f"test-agent-{uuid.uuid4().hex[:8]}",
        status=AgentStatus.PUBLISHED,
    )
    db_session.add(agent)
    await db_session.commit()

    yield agent

    await db_session.execute(delete(Agent).where(Agent.id == agent.id))
    await db_session.execute(delete(Organization).where(Organization.id == org.id))
    await db_session.commit()
