"""EndUser identity binding — maps callers (phone / SIP URI / chatbot id) to UUIDs.

The UUIDs we mint here are what we hand to Agno's MemoryManager as
``user_id``. Agno keys its facts on that string; without a stable
per-caller UUID, two calls from the same person would produce two memory
namespaces and the agent would forget the user between calls.

Per-agent identity scope: same phone calling Agent A and Agent B yields
two distinct EndUser rows. Cross-agent unification is intentionally out
of scope (different tenancy contexts; see plan).

Two identifier dimensions, dispatched by ``normalize_phone``:
- parses as a valid phone → ``end_users.phone_number`` (E.164)
- doesn't parse (chatbot user_id, SIP URI from a Plivo Endpoint) →
  ``end_users.external_id``

Both upserts are race-safe: Postgres ``INSERT ... ON CONFLICT DO UPDATE
RETURNING`` against the partial unique indexes from alembic 004. Two
concurrent inbound webhooks for the same caller can't double-insert.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.end_user import EndUser
from app.services.phone_normalizer import normalize_phone


class EndUserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_or_create_by_caller(
        self,
        agent_id: uuid.UUID,
        raw_id: str | None,
        name: str | None = None,
    ) -> EndUser | None:
        """Resolve a raw caller identifier to an EndUser row, creating if needed.

        ``raw_id`` is whatever the channel handed us:
        - voice (PSTN inbound): the From number, e.g. ``"+919876543210"``
        - voice (SIP Endpoint demo): a SIP URI, e.g. ``"sip:agentstudio…@…"``
        - WhatsApp: the sender's phone
        - chatbot: caller-supplied ``user_id`` string

        Empty / None / whitespace-only → returns None (anonymous; caller
        should set ``end_user_id=None`` on the Conversation and skip
        memory binding for the call).

        **Dev-only SIP alias.** If ``raw_id`` exactly matches a configured
        ``DEV_SIP_ALIAS_URI`` (set in .env), it's substituted with the
        corresponding phone number before normalization — so a Plivo SIP
        softphone caller unifies with their WhatsApp/chatbot EndUser
        without needing a real PSTN DID. Empty in production.
        """
        if not raw_id or not raw_id.strip():
            return None

        stripped = raw_id.strip()
        aliased = settings.dev_sip_phone_aliases.get(stripped)
        if aliased is not None:
            stripped = aliased  # route through phone path

        phone = normalize_phone(stripped)
        if phone:
            return await self._upsert_by_phone(agent_id, phone, name)
        return await self._upsert_by_external_id(agent_id, raw_id.strip(), name)

    async def _upsert_by_phone(
        self,
        agent_id: uuid.UUID,
        phone: str,
        name: str | None,
    ) -> EndUser:
        """Atomic upsert against ``uq_end_users_agent_phone`` (partial unique).

        ``index_where`` is required for Postgres to match the partial unique
        index — without it, ON CONFLICT raises "no unique constraint matches".

        Name preservation: if a row already exists with a name and we're
        called without one (or with the same name), we don't clobber it.
        ``COALESCE(EXCLUDED.name, end_users.name)`` keeps the first non-null
        name we ever saw — so a later anonymous call doesn't erase
        Aarti's name from a prior call where she introduced herself.
        """
        ins = pg_insert(EndUser).values(
            agent_id=agent_id, phone_number=phone, name=name,
        )
        stmt = ins.on_conflict_do_update(
            index_elements=["agent_id", "phone_number"],
            index_where=EndUser.phone_number.is_not(None),
            set_={
                "last_seen_at": func.now(),
                "name": func.coalesce(ins.excluded.name, EndUser.name),
                "updated_at": func.now(),
            },
        ).returning(EndUser)
        # SQLAlchemy needs ``execution_options(populate_existing=True)`` plus a
        # scalars().one() to materialise the RETURNING row as a real ORM
        # object the caller can use (e.g. read .id immediately).
        result = await self.db.execute(
            stmt, execution_options={"populate_existing": True},
        )
        await self.db.commit()
        return result.scalar_one()

    async def _upsert_by_external_id(
        self,
        agent_id: uuid.UUID,
        external_id: str,
        name: str | None,
    ) -> EndUser:
        """Atomic upsert against ``uq_end_users_agent_external`` (partial unique).

        Mirror of ``_upsert_by_phone`` but keyed on ``external_id``. Used for
        chatbot user_ids and SIP URIs where ``phonenumbers`` failed to parse.
        """
        ins = pg_insert(EndUser).values(
            agent_id=agent_id, external_id=external_id, name=name,
        )
        stmt = ins.on_conflict_do_update(
            index_elements=["agent_id", "external_id"],
            index_where=EndUser.external_id.is_not(None),
            set_={
                "last_seen_at": func.now(),
                "name": func.coalesce(ins.excluded.name, EndUser.name),
                "updated_at": func.now(),
            },
        ).returning(EndUser)
        result = await self.db.execute(
            stmt, execution_options={"populate_existing": True},
        )
        await self.db.commit()
        return result.scalar_one()

    async def increment_conversation_count(self, end_user_id: uuid.UUID) -> None:
        """Bump ``total_conversations`` atomically.

        Atomic via a single UPDATE — no read-then-write race even under
        concurrent calls. Used by the orchestrator after a Conversation
        successfully starts for this end user.
        """
        await self.db.execute(
            update(EndUser)
            .where(EndUser.id == end_user_id)
            .values(total_conversations=EndUser.total_conversations + 1)
        )
        await self.db.commit()
