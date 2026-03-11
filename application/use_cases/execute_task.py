"""ExecuteTaskUseCase — load, execute, and persist a task."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from domain.entities.execution_record import ExecutionRecord
from domain.entities.task import TaskEntity
from domain.ports.execution_record_repository import ExecutionRecordRepository
from domain.ports.task_engine import TaskEngine
from domain.ports.task_repository import TaskRepository
from domain.ports.todo_manager import TodoManagerPort
from domain.services.topic_extractor import TopicExtractor
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType
from domain.value_objects.status import SubTaskStatus, TaskStatus

if TYPE_CHECKING:
    from application.use_cases.discover_tools import DiscoverToolsUseCase
    from application.use_cases.extract_insights import ExtractInsightsUseCase

logger = logging.getLogger(__name__)

# Topic string → TaskType mapping for execution records
_TOPIC_TO_TASK_TYPE: dict[str, TaskType] = {
    "frontend": TaskType.CODE_GENERATION,
    "backend": TaskType.CODE_GENERATION,
    "database": TaskType.CODE_GENERATION,
    "testing": TaskType.CODE_GENERATION,
    "refactoring": TaskType.CODE_GENERATION,
    "devops": TaskType.FILE_OPERATION,
    "documentation": TaskType.FILE_OPERATION,
    "ml": TaskType.COMPLEX_REASONING,
    "security": TaskType.COMPLEX_REASONING,
    "data": TaskType.LONG_CONTEXT,
}


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
        discover_tools: DiscoverToolsUseCase | None = None,
        execution_record_repo: ExecutionRecordRepository | None = None,
        default_model: str = "ollama/qwen3:8b",
    ) -> None:
        self._engine = engine
        self._repo = repo
        self._todo = todo
        self._extract_insights = extract_insights
        self._discover_tools = discover_tools
        self._execution_record_repo = execution_record_repo
        self._default_model = default_model

    async def execute(
        self,
        task_id: str,
        engine_type: AgentEngineType = AgentEngineType.OLLAMA,
        model_used: str | None = None,
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

        t0 = time.monotonic()
        result = await self._engine.execute(task)
        duration_s = time.monotonic() - t0

        # Determine final status from subtask outcomes
        if result.success_rate == 1.0:
            result.status = TaskStatus.SUCCESS
        elif result.success_rate > 0:
            result.status = TaskStatus.FALLBACK
        else:
            result.status = TaskStatus.FAILED

        result.total_cost_usd = sum(s.cost_usd for s in result.subtasks)

        # Record execution for self-evolution (fire-and-forget, never blocks)
        await self._safe_record_execution(
            result, engine_type, duration_s, model_used or self._default_model
        )

        # UCL: extract insights from subtask outputs (never blocks execution)
        await self._safe_extract_insights(result, engine_type)

        # Auto-discover tools on failure (fire-and-forget, never blocks)
        if result.status in (TaskStatus.FAILED, TaskStatus.FALLBACK):
            await self._safe_suggest_tools(result)

        # Principle 4: update todo.md after execution
        if self._todo:
            self._todo.update_from_task(result)

        await self._repo.update(result)
        return result

    @staticmethod
    def _infer_task_type(goal: str) -> TaskType:
        """Map task goal → TaskType via TopicExtractor."""
        topic = TopicExtractor.extract(goal)
        return _TOPIC_TO_TASK_TYPE.get(topic, TaskType.SIMPLE_QA)

    async def _safe_record_execution(
        self,
        task: TaskEntity,
        engine_type: AgentEngineType,
        duration_s: float,
        model_used: str,
    ) -> None:
        """Build and save an ExecutionRecord. Fire-and-forget, never blocks."""
        if self._execution_record_repo is None:
            return

        # Collect first error from failed subtasks
        error_message: str | None = None
        for st in task.subtasks:
            if st.status == SubTaskStatus.FAILED and st.error:
                error_message = st.error
                break

        record = ExecutionRecord(
            task_id=task.id,
            task_type=self._infer_task_type(task.goal),
            goal=task.goal,
            engine_used=engine_type,
            model_used=model_used,
            success=task.status == TaskStatus.SUCCESS,
            error_message=error_message,
            cost_usd=task.total_cost_usd,
            duration_seconds=duration_s,
            cache_hit_rate=0.0,
        )

        try:
            await self._execution_record_repo.save(record)
        except Exception:
            logger.warning(
                "Failed to record execution for task %s — continuing",
                task.id,
                exc_info=True,
            )

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

    async def _safe_suggest_tools(self, task: TaskEntity) -> None:
        """Suggest tools based on subtask errors. Fire-and-forget, never blocks."""
        if self._discover_tools is None:
            return

        errors: list[str] = []
        for st in task.subtasks:
            if st.status == SubTaskStatus.FAILED and st.error:
                errors.append(st.error)

        if not errors:
            return

        combined_error = "\n".join(errors)
        try:
            suggestions = await self._discover_tools.suggest_for_failure(
                error_message=combined_error,
                task_description=task.goal,
            )
            if suggestions.suggestions:
                names = [s.name for s in suggestions.suggestions]
                logger.info(
                    "Tool suggestions for task %s: %s",
                    task.id,
                    ", ".join(names),
                )
        except Exception:
            logger.warning(
                "Tool suggestion failed for task %s — continuing",
                task.id,
                exc_info=True,
            )
