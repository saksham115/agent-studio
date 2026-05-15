"""Celery beat task: WhatsApp idle-sweep memory writer.

WhatsApp has no clean termination signal (no Plivo-style hangup, no
chatbot ``end_session`` call). Without this task, info shared on
WhatsApp would never be extracted to long-term memory and voice / chatbot
turns couldn't recall it.

This task runs every ``MEMORY_SWEEP_INTERVAL_SECONDS`` (registered on
the beat schedule in ``celery_app.py``). Each tick:

1. Picks up to 50 conversations that are ACTIVE, idle past the threshold,
   memory-unwritten, end-user-linked, and below the retry cap.
2. Acquires row locks via ``SELECT ... FOR UPDATE SKIP LOCKED`` — this is
   queue-draining semantics (concurrent workers skip each other's
   in-flight rows). Note: this is DIFFERENT from the idempotency guard in
   ``_post_call_memory_write``, which uses bare ``FOR UPDATE`` (blocking)
   because there idempotency is the goal.
3. Commits immediately to release the SELECT-locks; per-row processing
   happens in independent transactions via ``_post_call_memory_write``.
4. Fans out under an ``asyncio.Semaphore(8)`` to rate-limit concurrent
   LLM extraction calls — protects against Pellet / Anthropic rate limits
   during catch-up after an outage. (Process-local: multi-worker scale-out
   would need a Redis token bucket; documented assumption for v1.)
5. ``_post_call_memory_write(..., close_conversation=True)`` writes
   ``memory_written_at`` + ``status=COMPLETED`` + ``ended_at`` in one
   atomic transaction on success; on failure it increments
   ``memory_extraction_attempts`` and the row stays sweep-eligible until
   the attempts cap.

Worker pool compatibility: Celery's default ``prefork`` pool works with
``asyncio.run()``. ``gevent`` / ``eventlet`` pools monkey-patch I/O in
ways that conflict with asyncio — if a future deploy uses those pools,
restrict the beat task to prefork via ``CELERY_TASK_ROUTES`` or convert
this body to a sync implementation.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from opentelemetry import trace
from sqlalchemy import select

from app.config import settings
from app.models.conversation import Conversation, ConversationStatus
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# Process-local concurrency cap. Tightens to 8 concurrent LLM extraction
# calls during catch-up — Anthropic Sonnet's org-wide RPM is ~50, Haiku
# higher; Pellet's limits are private. 8 keeps headroom for the rest of
# the application's LLM traffic.
_BATCH_LIMIT = 50
_LLM_CONCURRENCY = 8


@celery_app.task(name="memory.extract_idle_conversations")
def extract_idle_conversations_task() -> dict:
    """Sync wrapper: Celery default prefork pool runs sync; we bridge to async.

    asyncio.run() creates a fresh event loop per task invocation. memory.py's
    per-loop singleton (stored on the loop object) rebuilds the Agno
    components in this loop — no stale pool errors. The loop is closed at
    asyncio.run() exit, which GCs the singleton attached to it.
    """
    return asyncio.run(_extract_idle_conversations_async())


async def _extract_idle_conversations_async() -> dict:
    """Async body of the sweep. Returns a small report dict for logging."""
    # Lazy imports — avoid pulling webhooks router into Celery's import graph
    # at module load; only loaded when the task fires.
    from app.api.v1.webhooks import _post_call_memory_write
    from app.database import async_session_factory

    threshold_min = settings.effective_idle_threshold_minutes
    semaphore = asyncio.Semaphore(_LLM_CONCURRENCY)

    with tracer.start_as_current_span("memory.extract_idle_conversations") as span:
        span.set_attribute("threshold_minutes", threshold_min)
        span.set_attribute("batch_limit", _BATCH_LIMIT)
        span.set_attribute("llm_concurrency", _LLM_CONCURRENCY)

        # Phase 1: pick candidates under a brief lock window.
        async with async_session_factory() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=threshold_min)
            stmt = (
                select(
                    Conversation.id,
                    Conversation.end_user_id,
                    Conversation.agent_id,
                )
                .where(
                    Conversation.status == ConversationStatus.ACTIVE,
                    Conversation.last_message_at < cutoff,
                    Conversation.memory_written_at.is_(None),
                    Conversation.end_user_id.is_not(None),
                    Conversation.memory_extraction_attempts
                    < settings.MEMORY_MAX_EXTRACTION_ATTEMPTS,
                )
                .order_by(Conversation.last_message_at.asc())
                .limit(_BATCH_LIMIT)
                .with_for_update(skip_locked=True)
            )
            candidates = list((await db.execute(stmt)).all())
            # Commit immediately to release the SELECT FOR UPDATE row locks
            # — the actual extraction below opens fresh sessions per row, so
            # holding these locks during 25+ seconds of LLM extraction would
            # block any concurrent UPDATE on those rows (e.g. a new message
            # bumping last_message_at).
            await db.commit()

        span.set_attribute("batch.size", len(candidates))
        if not candidates:
            span.set_attribute("processed.count", 0)
            span.set_attribute("failures.count", 0)
            return {"batch_size": 0, "processed": 0, "failures": 0}

        # Phase 2: fan out extraction under the concurrency cap.
        processed = 0
        failures = 0

        async def _process(conv_id, end_user_id, agent_id) -> None:
            nonlocal processed, failures
            async with semaphore:
                try:
                    await _post_call_memory_write(
                        conv_id, end_user_id, agent_id, close_conversation=True,
                    )
                    processed += 1
                except Exception:
                    logger.exception("Sweep extraction crashed for %s", conv_id)
                    failures += 1

        await asyncio.gather(
            *[_process(c.id, c.end_user_id, c.agent_id) for c in candidates]
        )

        span.set_attribute("processed.count", processed)
        span.set_attribute("failures.count", failures)
        logger.info(
            "Idle sweep complete: batch_size=%d processed=%d failures=%d",
            len(candidates), processed, failures,
        )
        return {
            "batch_size": len(candidates),
            "processed": processed,
            "failures": failures,
        }
