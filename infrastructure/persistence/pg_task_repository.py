"""PostgreSQL TaskRepository — maps TaskEntity <-> TaskModel via async SQLAlchemy."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from domain.entities.task import SubTask, TaskEntity
from domain.ports.task_repository import TaskRepository
from domain.value_objects.status import SubTaskStatus, TaskStatus
from infrastructure.persistence.models import TaskModel


class PgTaskRepository(TaskRepository):
    """Production-grade PostgreSQL repository for tasks."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # ── Mapping helpers ──

    @staticmethod
    def _subtask_to_dict(st: SubTask) -> dict:
        """Serialize a SubTask to a JSON-friendly dict for JSONB storage."""
        return {
            "id": st.id,
            "description": st.description,
            "status": st.status.value,
            "dependencies": st.dependencies,
            "result": st.result,
            "error": st.error,
            "model_used": st.model_used,
            "cost_usd": st.cost_usd,
            "engine_used": st.engine_used,
            "complexity": st.complexity.value if st.complexity else None,
            "react_iterations": st.react_iterations,
            "tool_calls_count": st.tool_calls_count,
            "tools_used": st.tools_used,
            "data_sources": st.data_sources,
            "code": st.code,
            "execution_output": st.execution_output,
            "spawned_by_reflection": st.spawned_by_reflection,
            "reflection_round": st.reflection_round,
        }

    @staticmethod
    def _to_model(task: TaskEntity) -> TaskModel:
        subtasks_json = [
            PgTaskRepository._subtask_to_dict(st)
            for st in task.subtasks
        ]
        return TaskModel(
            id=(
                uuid.UUID(task.id)
                if len(task.id) == 36
                else uuid.uuid5(uuid.NAMESPACE_DNS, task.id)
            ),
            goal=task.goal,
            status=task.status.value,
            depth=0,
            metadata_={"subtasks": subtasks_json, "total_cost_usd": task.total_cost_usd},
            final_answer=task.final_answer,
            created_at=task.created_at,
        )

    @staticmethod
    def _dict_to_subtask(s: dict) -> SubTask:
        """Deserialize a SubTask from a JSONB dict."""
        from domain.value_objects.task_complexity import TaskComplexity

        complexity_raw = s.get("complexity")
        complexity = TaskComplexity(complexity_raw) if complexity_raw else None
        return SubTask(
            id=s["id"],
            description=s["description"],
            status=SubTaskStatus(s["status"]),
            dependencies=s.get("dependencies", []),
            result=s.get("result"),
            error=s.get("error"),
            model_used=s.get("model_used"),
            cost_usd=s.get("cost_usd", 0.0),
            engine_used=s.get("engine_used"),
            complexity=complexity,
            react_iterations=s.get("react_iterations", 0),
            tool_calls_count=s.get("tool_calls_count", 0),
            tools_used=s.get("tools_used", []),
            data_sources=s.get("data_sources", []),
            code=s.get("code"),
            execution_output=s.get("execution_output"),
            spawned_by_reflection=s.get("spawned_by_reflection", False),
            reflection_round=s.get("reflection_round"),
        )

    @staticmethod
    def _to_entity(model: TaskModel) -> TaskEntity:
        meta = model.metadata_ or {}
        subtasks_data = meta.get("subtasks", [])
        subtasks = [
            PgTaskRepository._dict_to_subtask(s)
            for s in subtasks_data
        ]
        return TaskEntity(
            id=str(model.id),
            goal=model.goal,
            status=TaskStatus(model.status),
            subtasks=subtasks,
            total_cost_usd=meta.get("total_cost_usd", 0.0),
            created_at=model.created_at,
            final_answer=model.final_answer,
        )

    # ── Repository interface ──

    async def save(self, task: TaskEntity) -> None:
        async with self._session_factory() as session:
            model = self._to_model(task)
            session.add(model)
            await session.commit()

    async def get_by_id(self, task_id: str) -> TaskEntity | None:
        async with self._session_factory() as session:
            try:
                uid = uuid.UUID(task_id)
            except ValueError:
                return None
            result = await session.get(TaskModel, uid)
            if result is None:
                return None
            return self._to_entity(result)

    async def list_all(self) -> list[TaskEntity]:
        async with self._session_factory() as session:
            stmt = select(TaskModel).order_by(TaskModel.created_at.desc())
            result = await session.execute(stmt)
            return [self._to_entity(row) for row in result.scalars().all()]

    async def list_by_status(self, status: TaskStatus) -> list[TaskEntity]:
        async with self._session_factory() as session:
            stmt = select(TaskModel).where(TaskModel.status == status.value)
            result = await session.execute(stmt)
            return [self._to_entity(row) for row in result.scalars().all()]

    async def update(self, task: TaskEntity) -> None:
        async with self._session_factory() as session:
            try:
                uid = uuid.UUID(task.id)
            except ValueError:
                return
            model = await session.get(TaskModel, uid)
            if model is None:
                # Upsert: save if not found
                model = self._to_model(task)
                session.add(model)
            else:
                model.goal = task.goal
                model.status = task.status.value
                subtasks_json = [
                    PgTaskRepository._subtask_to_dict(st)
                    for st in task.subtasks
                ]
                model.metadata_ = {"subtasks": subtasks_json, "total_cost_usd": task.total_cost_usd}
                model.final_answer = task.final_answer
            await session.commit()

    async def delete(self, task_id: str) -> None:
        async with self._session_factory() as session:
            try:
                uid = uuid.UUID(task_id)
            except ValueError:
                return
            # Delete referencing plans first (FK constraint)
            from infrastructure.persistence.models import PlanModel

            plan_stmt = select(PlanModel).where(PlanModel.task_id == uid)
            for plan in (await session.execute(plan_stmt)).scalars():
                await session.delete(plan)
            model = await session.get(TaskModel, uid)
            if model is not None:
                await session.delete(model)
                await session.commit()
