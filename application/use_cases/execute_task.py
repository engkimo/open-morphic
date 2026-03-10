"""ExecuteTaskUseCase — load, execute, and persist a task."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from domain.entities.task import TaskEntity
from domain.ports.task_engine import TaskEngine
from domain.ports.task_repository import TaskRepository
from domain.ports.todo_manager import TodoManagerPort
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.status import SubTaskStatus, TaskStatus

if TYPE_CHECKING:
    from application.use_cases.extract_insights import ExtractInsightsUseCase

logger = logging.getLogger(__name__)


class TaskNotFoundError(Exception):
    def __init__(self, task_id: str) -> None:
        super().__init__(f"Task not found: {task_id}")
        self.task_id = task_id


class ExecuteTaskUseCase:
    def __init__(
        self,
        engine: TaskEngine,
        repo: TaskRepository,
        todo: TodoManagerPort | None = None,
        extract_insights: ExtractInsightsUseCase | None = None,
    ) -> None:
        self._engine = engine
        self._repo = repo
        self._todo = todo
        self._extract_insights = extract_insights

    async def execute(
        self,
        task_id: str,
        engine_type: AgentEngineType = AgentEngineType.OLLAMA,
    ) -> TaskEntity:
        """Load task, run through engine, update final status, and persist."""
        task = await self._repo.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)

        task.status = TaskStatus.RUNNING
        await self._repo.update(task)

        # Principle 4: update todo.md before execution
        if self._todo:
            self._todo.update_from_task(task)

        result = await self._engine.execute(task)

        # Determine final status from subtask outcomes
        if result.success_rate == 1.0:
            result.status = TaskStatus.SUCCESS
        elif result.success_rate > 0:
            result.status = TaskStatus.FALLBACK
        else:
            result.status = TaskStatus.FAILED

        result.total_cost_usd = sum(s.cost_usd for s in result.subtasks)

        # UCL: extract insights from subtask outputs (never blocks execution)
        await self._safe_extract_insights(result, engine_type)

        # Principle 4: update todo.md after execution
        if self._todo:
            self._todo.update_from_task(result)

        await self._repo.update(result)
        return result

    async def _safe_extract_insights(
        self,
        task: TaskEntity,
        engine_type: AgentEngineType,
    ) -> None:
        """Gather subtask results/errors and run insight extraction.

        Wrapped in try/except — extraction failure must never block execution.
        """
        if self._extract_insights is None:
            return

        # Combine subtask results and errors into a single output string
        parts: list[str] = []
        for st in task.subtasks:
            if st.result:
                parts.append(st.result)
            if st.status == SubTaskStatus.FAILED and st.error:
                parts.append(f"ERROR: {st.error}")

        combined = "\n".join(parts)
        if not combined.strip():
            return

        try:
            await self._extract_insights.extract_and_store(
                task_id=task.id,
                engine=engine_type,
                output=combined,
            )
        except Exception:
            logger.warning(
                "Insight extraction failed for task %s — continuing",
                task.id,
                exc_info=True,
            )
