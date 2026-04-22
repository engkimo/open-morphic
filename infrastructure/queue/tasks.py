"""Celery task definitions — async task execution via worker process."""

from __future__ import annotations

import asyncio
import logging

from infrastructure.queue.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="morphic.execute_task", max_retries=2)
def execute_task_worker(self, task_id: str) -> dict[str, str]:  # noqa: ANN001
    """Execute a task DAG in a Celery worker process.

    Creates its own AppContainer (PG repos) to run independently of the API.
    """
    try:
        return asyncio.run(_execute_async(task_id))
    except Exception as exc:
        logger.exception("Task %s failed: %s", task_id, exc)
        raise self.retry(exc=exc, countdown=5) from exc


async def _execute_async(task_id: str) -> dict[str, str]:
    """Async inner function — creates container and runs ExecuteTaskUseCase."""
    from interface.api.container import AppContainer
    from shared.config import Settings

    settings = Settings(use_postgres=True)
    container = AppContainer(settings=settings)
    await container.init()

    try:
        result = await container.execute_task.execute(task_id)
        return {"task_id": result.id, "status": result.status.value}
    finally:
        await container.close()
