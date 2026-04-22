"""PostgreSQL PlanRepository — maps ExecutionPlan <-> PlanModel."""

from __future__ import annotations

import contextlib
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from domain.entities.plan import ExecutionPlan, PlanStep
from domain.ports.plan_repository import PlanRepository
from domain.value_objects.status import PlanStatus
from infrastructure.persistence.models import PlanModel


class PgPlanRepository(PlanRepository):
    """PostgreSQL repository for execution plans."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _to_model(plan: ExecutionPlan) -> PlanModel:
        steps_json = [
            {
                "subtask_description": s.subtask_description,
                "proposed_model": s.proposed_model,
                "estimated_cost_usd": s.estimated_cost_usd,
                "estimated_tokens": s.estimated_tokens,
                "risk_note": s.risk_note,
            }
            for s in plan.steps
        ]
        task_uuid = None
        if plan.task_id:
            with contextlib.suppress(ValueError):
                task_uuid = uuid.UUID(plan.task_id)
        plan_uuid = (
            uuid.UUID(plan.id) if len(plan.id) == 36 else uuid.uuid5(uuid.NAMESPACE_DNS, plan.id)
        )
        return PlanModel(
            id=plan_uuid,
            goal=plan.goal,
            status=plan.status.value,
            steps=steps_json,
            total_estimated_cost_usd=Decimal(str(plan.total_estimated_cost_usd)),
            task_id=task_uuid,
            created_at=plan.created_at,
        )

    @staticmethod
    def _to_entity(model: PlanModel) -> ExecutionPlan:
        steps_data = model.steps or []
        steps = [
            PlanStep(
                subtask_description=s["subtask_description"],
                proposed_model=s.get("proposed_model", "ollama/qwen3:8b"),
                estimated_cost_usd=s.get("estimated_cost_usd", 0.0),
                estimated_tokens=s.get("estimated_tokens", 0),
                risk_note=s.get("risk_note", ""),
            )
            for s in steps_data
        ]
        return ExecutionPlan(
            id=str(model.id),
            goal=model.goal,
            status=PlanStatus(model.status),
            steps=steps,
            total_estimated_cost_usd=float(model.total_estimated_cost_usd),
            task_id=str(model.task_id) if model.task_id else None,
            created_at=model.created_at,
        )

    async def save(self, plan: ExecutionPlan) -> None:
        async with self._session_factory() as session:
            session.add(self._to_model(plan))
            await session.commit()

    async def get_by_id(self, plan_id: str) -> ExecutionPlan | None:
        async with self._session_factory() as session:
            try:
                uid = uuid.UUID(plan_id)
            except ValueError:
                return None
            result = await session.get(PlanModel, uid)
            if result is None:
                return None
            return self._to_entity(result)

    async def list_all(self) -> list[ExecutionPlan]:
        async with self._session_factory() as session:
            stmt = select(PlanModel).order_by(PlanModel.created_at.desc())
            result = await session.execute(stmt)
            return [self._to_entity(row) for row in result.scalars().all()]

    async def update(self, plan: ExecutionPlan) -> None:
        async with self._session_factory() as session:
            try:
                uid = uuid.UUID(plan.id)
            except ValueError:
                return
            model = await session.get(PlanModel, uid)
            if model is None:
                session.add(self._to_model(plan))
            else:
                model.goal = plan.goal
                model.status = plan.status.value
                model.steps = [
                    {
                        "subtask_description": s.subtask_description,
                        "proposed_model": s.proposed_model,
                        "estimated_cost_usd": s.estimated_cost_usd,
                        "estimated_tokens": s.estimated_tokens,
                        "risk_note": s.risk_note,
                    }
                    for s in plan.steps
                ]
                model.total_estimated_cost_usd = Decimal(str(plan.total_estimated_cost_usd))
                if plan.task_id:
                    with contextlib.suppress(ValueError):
                        model.task_id = uuid.UUID(plan.task_id)
            await session.commit()
