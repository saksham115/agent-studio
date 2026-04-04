"""Celery application for background task processing."""

from celery import Celery

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
)

# Auto-discover tasks from workers module
celery_app.autodiscover_tasks(["app.workers"])
