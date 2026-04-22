"""InteractivePlanUseCase — Devin-style plan creation, review, approve/reject."""

from __future__ import annotations

from application.use_cases.cost_estimator import CostEstimator
from domain.entities.plan import ExecutionPlan, PlanStep
from domain.entities.task import TaskEntity
from domain.ports.plan_repository import PlanRepository
from domain.ports.task_engine import TaskEngine
from domain.ports.task_repository import TaskRepository
from domain.value_objects.status import PlanStatus
from domain.value_objects.task_complexity import TaskComplexity


class PlanNotFoundError(Exception):
    def __init__(self, plan_id: str) -> None:
        super().__init__(f"Plan not found: {plan_id}")
        self.plan_id = plan_id


class PlanAlreadyDecidedError(Exception):
    def __init__(self, plan_id: str, status: str) -> None:
        super().__init__(f"Plan {plan_id} already {status}")


class InteractivePlanUseCase:
    """Create, review, approve, or reject execution plans."""

    def __init__(
        self,
        engine: TaskEngine,
        cost_estimator: CostEstimator,
        plan_repo: PlanRepository,
        task_repo: TaskRepository,
    ) -> None:
        self._engine = engine
        self._cost_estimator = cost_estimator
        self._plan_repo = plan_repo
        self._task_repo = task_repo

    async def create_plan(
        self,
        goal: str,
        model: str = "ollama/qwen3:8b",
    ) -> ExecutionPlan:
        """Decompose goal into subtasks and estimate cost. Returns PROPOSED plan."""
        # Use intent analyzer to decompose into SubTask objects
        subtasks = await self._engine.decompose(goal)
        subtask_descriptions = [st.description for st in subtasks] if subtasks else [goal]

        estimates = self._cost_estimator.estimate(subtask_descriptions, model)

        # Build preferred_model and complexity lookups from decomposed subtasks
        pref_map: dict[str, str | None] = {}
        complexity_map: dict[str, TaskComplexity | None] = {}
        if subtasks:
            for st in subtasks:
                pref_map[st.description] = st.preferred_model
                complexity_map[st.description] = st.complexity

        # Build artifact flow lookups from decomposed subtasks
        produces_map: dict[str, list[str]] = {}
        consumes_map: dict[str, list[str]] = {}
        if subtasks:
            for st in subtasks:
                produces_map[st.description] = (
                    list(st.output_artifacts.keys()) if st.output_artifacts else []
                )
                consumes_map[st.description] = (
                    list(st.input_artifacts.keys()) if st.input_artifacts else []
                )

        steps = [
            PlanStep(
                subtask_description=est.description,
                proposed_model=pref_map.get(est.description) or est.model,
                estimated_cost_usd=est.estimated_cost_usd,
                estimated_tokens=est.estimated_tokens,
                preferred_model=pref_map.get(est.description),
                complexity=complexity_map.get(est.description),
                produces=produces_map.get(est.description, []),
                consumes=consumes_map.get(est.description, []),
            )
            for est in estimates
        ]

        plan = ExecutionPlan(
            goal=goal,
            steps=steps,
            total_estimated_cost_usd=sum(s.estimated_cost_usd for s in steps),
            status=PlanStatus.PROPOSED,
        )
        await self._plan_repo.save(plan)
        return plan

    async def approve_plan(self, plan_id: str) -> TaskEntity:
        """Approve a plan: create TaskEntity, persist, return ready for execution."""
        plan = await self._plan_repo.get_by_id(plan_id)
        if plan is None:
            raise PlanNotFoundError(plan_id)
        if plan.status != PlanStatus.PROPOSED:
            raise PlanAlreadyDecidedError(plan_id, plan.status.value)

        # Create task from plan — preserve preferred_model for engine routing
        from domain.entities.task import SubTask

        subtasks = [
            SubTask(
                description=step.subtask_description,
                model_used=step.proposed_model,
                preferred_model=step.preferred_model,
                complexity=step.complexity,
                output_artifacts={name: "" for name in step.produces} if step.produces else {},
                input_artifacts={name: "" for name in step.consumes} if step.consumes else {},
            )
            for step in plan.steps
        ]

        # TD-097: Re-infer dependencies from artifact flow.
        # PlanSteps don't carry dependency IDs (since SubTask IDs are
        # regenerated here), so we resolve them from produces/consumes.
        from domain.services.artifact_dependency_resolver import ArtifactDependencyResolver

        ArtifactDependencyResolver.resolve(subtasks)

        task = TaskEntity(goal=plan.goal, subtasks=subtasks)
        await self._task_repo.save(task)

        # Update plan status
        plan.status = PlanStatus.APPROVED
        plan.task_id = task.id
        await self._plan_repo.update(plan)

        return task

    async def reject_plan(self, plan_id: str) -> ExecutionPlan:
        """Reject a plan."""
        plan = await self._plan_repo.get_by_id(plan_id)
        if plan is None:
            raise PlanNotFoundError(plan_id)
        if plan.status != PlanStatus.PROPOSED:
            raise PlanAlreadyDecidedError(plan_id, plan.status.value)

        plan.status = PlanStatus.REJECTED
        await self._plan_repo.update(plan)
        return plan

    async def get_plan(self, plan_id: str) -> ExecutionPlan:
        """Get a plan by ID."""
        plan = await self._plan_repo.get_by_id(plan_id)
        if plan is None:
            raise PlanNotFoundError(plan_id)
        return plan
