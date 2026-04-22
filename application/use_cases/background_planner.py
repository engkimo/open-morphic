"""BackgroundPlannerUseCase — Windsurf-style continuous plan refinement.

Advisory only: monitors task state and generates recommendations on failure.
Does NOT auto-modify running tasks.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from domain.ports.llm_gateway import LLMGateway
from domain.ports.task_repository import TaskRepository
from domain.value_objects.status import SubTaskStatus, TaskStatus

logger = logging.getLogger(__name__)


class BackgroundPlannerUseCase:
    """Monitor a running task and generate advisory recommendations."""

    def __init__(
        self,
        llm: LLMGateway,
        task_repo: TaskRepository,
        poll_interval: float = 5.0,
    ) -> None:
        self._llm = llm
        self._task_repo = task_repo
        self._poll_interval = poll_interval
        self._running_tasks: dict[str, asyncio.Task[None]] = {}
        self._recommendations: dict[str, list[str]] = {}

    async def start(self, task_id: str) -> None:
        """Start background monitoring for a task. Idempotent."""
        if task_id in self._running_tasks and not self._running_tasks[task_id].done():
            return  # Already monitoring
        self._recommendations[task_id] = []
        self._running_tasks[task_id] = asyncio.create_task(self._monitor_loop(task_id))

    async def stop(self, task_id: str) -> None:
        """Stop monitoring for a task."""
        bg_task = self._running_tasks.pop(task_id, None)
        if bg_task is not None and not bg_task.done():
            bg_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await bg_task

    def get_recommendations(self, task_id: str) -> list[str]:
        """Get current advisory recommendations for a task."""
        return list(self._recommendations.get(task_id, []))

    async def _monitor_loop(self, task_id: str) -> None:
        """Poll task state and generate recommendations on failure."""
        try:
            while True:
                task = await self._task_repo.get_by_id(task_id)
                if task is None:
                    logger.warning("Background planner: task %s not found", task_id)
                    break

                # Check for failures and generate recommendations
                failed_subtasks = [st for st in task.subtasks if st.status == SubTaskStatus.FAILED]
                if failed_subtasks:
                    for st in failed_subtasks:
                        rec = f"Subtask '{st.description}' failed"
                        if st.error:
                            rec += f": {st.error}"
                        rec += " — consider retry with different model or fallback approach"
                        if rec not in self._recommendations.get(task_id, []):
                            self._recommendations.setdefault(task_id, []).append(rec)

                # Stop monitoring when task completes
                if task.status in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.FALLBACK):
                    logger.info(
                        "Background planner: task %s completed (%s)",
                        task_id,
                        task.status.value,
                    )
                    break

                await asyncio.sleep(self._poll_interval)
        except asyncio.CancelledError:
            logger.info("Background planner: monitoring cancelled for %s", task_id)
        finally:
            self._running_tasks.pop(task_id, None)
