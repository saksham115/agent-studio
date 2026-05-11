"""Celery application for background task processing."""

from celery import Celery
from celery.schedules import schedule

from app.config import settings

celery_app = Celery(
    "agent_studio",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=300,  # 5 minutes
    task_time_limit=600,  # 10 minutes
    beat_schedule={
        # WhatsApp idle-sweep — runs every 5 min. Catches WhatsApp (no
        # hangup signal), chatbot abandoned sessions, and any voice call
        # where the hangup webhook didn't fire (defensive). Per-tick
        # batch cap is 50 conversations; one batch comfortably fits in
        # the 5-min interval even at worst-case LLM latency.
        "memory-extract-idle-conversations": {
            "task": "memory.extract_idle_conversations",
            "schedule": schedule(run_every=300.0),  # 5 minutes
        },
    },
)

# Auto-discover tasks from workers module — only picks up `tasks.py` by default.
celery_app.autodiscover_tasks(["app.workers"])

# Explicit import — the memory idle-sweep task lives in a non-default module name
# (`memory_tasks.py`) so autodiscover skips it. Importing here runs the
# @celery_app.task decorator at startup and registers the task.
import app.workers.memory_tasks  # noqa: E402, F401
