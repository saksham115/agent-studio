"""Service-test-specific fixtures."""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture(autouse=True)
def _reset_mem0_cache():
    """Clear ``app.services.memory._build_memory``'s lru_cache after each test.

    ``_build_memory`` is ``@lru_cache(maxsize=1)`` so it constructs at most
    one ``Memory`` instance per process. Tests that monkeypatch it
    would otherwise leak state between tests via the cache. Yields, then
    clears.
    """
    yield
    # Lazy import: only do this if the memory module was loaded by the test.
    # Importing memory.py runs the EmbedderFactory hijack and pulls voyageai —
    # tests that don't touch memory shouldn't pay that import cost.
    import sys
    mod = sys.modules.get("app.services.memory")
    if mod is not None:
        mod._build_memory.cache_clear()


# ---------------------------------------------------------------------------
# DB fixtures for tests that need real SQLAlchemy + Postgres
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Per-test AsyncSession against the dev Postgres.

    Each test gets its own session; rows it writes are tracked and deleted
    in teardown so tests don't pollute the dev DB. We don't wrap the
    session in a single transaction-rolled-back-on-exit because
    ``EndUserService`` commits internally (intentional — its callers are
    request-scoped and need the row immediately readable).

    Skips with a clear message if no DATABASE_URL is configured (CI / dry
    clones).
    """
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
    """A throwaway published Agent the EndUser FK can attach to.

    Created once per test and deleted on teardown along with any
    EndUsers that referenced it (CASCADE).
    """
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

    # Teardown: agent CASCADE deletes its EndUsers.
    await db_session.execute(delete(Agent).where(Agent.id == agent.id))
    await db_session.execute(delete(Organization).where(Organization.id == org.id))
    await db_session.commit()
