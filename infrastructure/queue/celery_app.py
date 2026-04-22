"""Celery application factory — broker=Redis, backend=Redis."""

from __future__ import annotations

from celery import Celery

from shared.config import settings


def create_celery_app() -> Celery:
    """Build the Celery app with Redis broker and backend."""
    app = Celery(
        "morphic_agent",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
    )
    # Auto-discover tasks module
    app.autodiscover_tasks(["infrastructure.queue"])
    return app


celery_app = create_celery_app()
