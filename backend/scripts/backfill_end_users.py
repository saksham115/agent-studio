"""Backfill ``conversations.end_user_id`` for pre-existing rows.

Run AFTER ``alembic upgrade head`` and AFTER deploying the new code, in
that order:

1. ``alembic upgrade head`` — schema lands; ``end_users`` table empty,
   all ``conversations.end_user_id`` NULL.
2. New code rolls out — fresh inbound calls / WA messages / chatbot
   sessions start populating ``end_users`` and setting ``end_user_id``
   on new Conversations.
3. ``python -m scripts.backfill_end_users`` — this script — sweeps the
   historical Conversations and binds them to the same EndUsers that
   step 2 has been creating, by matching ``external_user_phone`` /
   ``external_user_id``.

Idempotent: re-running finds the already-bound rows have no work left
and exits clean. Safe to run mid-deploy or repeatedly.

Memory backfill is OUT OF SCOPE — mem0 starts empty after this PR. We
deliberately don't replay old messages through ``mem0.add`` here:

- Each replay costs an LLM call (Pellet credits).
- mem0's extraction prompt is tuned for in-flight conversations, not
  cold archives — facts may be lower quality.
- The user-visible benefit is "the next call remembers you", which is
  served by populating memory forward-only.

If a future need arises to seed historical memory (the "Conversation
memory backfill" follow-up in the plan), it'll be a separate script.

Usage::

    cd backend && python -m scripts.backfill_end_users
    cd backend && python -m scripts.backfill_end_users --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.services.end_user_service import EndUserService


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("backfill_end_users")


async def backfill(dry_run: bool = False) -> tuple[int, int, int]:
    """Bind unbound Conversations to EndUsers. Returns (bound, orphan, skipped).

    - ``bound`` — Conversation rows updated with a freshly-resolved end_user_id.
    - ``orphan`` — distinct caller identifiers that ``EndUserService`` couldn't
      resolve (empty external_user_phone AND external_user_id; should be
      zero given the WHERE clause but kept as a guard).
    - ``skipped`` — rows already bound (returned from the count query as 0;
      tracked for the dry-run summary).
    """
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    bound = 0
    orphan = 0

    async with Session() as db:
        # Count what's already bound (informational only).
        already_bound = (await db.execute(text("""
            SELECT COUNT(*) FROM conversations WHERE end_user_id IS NOT NULL
        """))).scalar_one()
        logger.info("conversations already bound: %d", already_bound)

        # Distinct caller-identity tuples needing resolution. We group by
        # (agent_id, phone, ext) so each unique caller is resolved once even
        # if they have many conversations.
        rows = (await db.execute(text("""
            SELECT DISTINCT agent_id, external_user_phone, external_user_id
            FROM conversations
            WHERE end_user_id IS NULL
              AND (external_user_phone IS NOT NULL OR external_user_id IS NOT NULL)
        """))).all()
        logger.info("distinct caller identities to resolve: %d", len(rows))

        svc = EndUserService(db)
        for agent_id, phone, ext in rows:
            # Prefer phone over external_id when both happen to be set —
            # phone is the more durable identity (chatbot user_ids can
            # be regenerated client-side).
            raw = phone or ext

            if dry_run:
                # Read-only preview: count what WOULD bind without minting
                # an EndUser. We can't show the resolved end_user.id (we
                # haven't created one), but we show the caller identity so
                # the operator can sanity-check what's about to happen.
                count = (await db.execute(text("""
                    SELECT COUNT(*) FROM conversations
                    WHERE agent_id = :agent_id
                      AND end_user_id IS NULL
                      AND (
                          (external_user_phone = :phone AND :phone IS NOT NULL)
                          OR (external_user_id = :ext AND :ext IS NOT NULL)
                      )
                """), {"agent_id": agent_id, "phone": phone, "ext": ext})).scalar_one()
                logger.info(
                    "[dry-run] would bind %d conversations "
                    "(agent=%s phone=%r ext=%r raw=%r)",
                    count, agent_id, phone, ext, raw,
                )
                bound += count
                continue

            eu = await svc.get_or_create_by_caller(agent_id, raw)
            if not eu:
                logger.warning(
                    "could not resolve EndUser for agent=%s phone=%r ext=%r",
                    agent_id, phone, ext,
                )
                orphan += 1
                continue

            # The :phone / :ext IS NOT NULL guards prevent NULL=NULL
            # comparisons (which are always false in SQL but better to
            # be explicit so future readers don't second-guess).
            result = await db.execute(text("""
                UPDATE conversations
                SET end_user_id = :eu_id
                WHERE agent_id = :agent_id
                  AND end_user_id IS NULL
                  AND (
                      (external_user_phone = :phone AND :phone IS NOT NULL)
                      OR (external_user_id = :ext AND :ext IS NOT NULL)
                  )
            """), {"eu_id": eu.id, "agent_id": agent_id,
                   "phone": phone, "ext": ext})
            bound += result.rowcount or 0
            logger.info(
                "bound %d conversations to end_user=%s "
                "(agent=%s phone=%r ext=%r)",
                result.rowcount, eu.id, agent_id, phone, ext,
            )

        if not dry_run:
            await db.commit()

    await engine.dispose()
    return bound, orphan, already_bound


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would be bound without writing to the DB.",
    )
    args = parser.parse_args()

    bound, orphan, already = asyncio.run(backfill(dry_run=args.dry_run))

    mode = "[DRY-RUN]" if args.dry_run else "[APPLIED]"
    logger.info(
        "%s bound=%d orphan=%d already_bound_before_run=%d",
        mode, bound, orphan, already,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
