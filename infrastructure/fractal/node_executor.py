"""NodeExecutor — bridge between PlanNode and LangGraphTaskEngine.

Sprint 15.5: Converts fractal PlanNode into SubTask/TaskEntity for
execution by the inner engine (LangGraphTaskEngine), then applies
results back to the PlanNode.

Responsibilities:
  - PlanNode → SubTask conversion (to_subtask)
  - PlanNode → single-subtask TaskEntity creation (for inner engine)
  - Execute a terminal node via inner engine and apply results
  - Artifact chaining: inject previous node outputs into next node inputs
"""

from __future__ import annotations

import logging

from domain.entities.fractal_engine import PlanNode
from domain.entities.task import SubTask, TaskEntity
from domain.ports.task_engine import TaskEngine
from domain.services.task_complexity import TaskComplexityClassifier
from domain.value_objects.status import SubTaskStatus, TaskStatus

logger = logging.getLogger(__name__)


class NodeExecutor:
    """Executes terminal PlanNodes by delegating to the inner TaskEngine."""

    def __init__(self, inner_engine: TaskEngine) -> None:
        self._inner = inner_engine

    async def execute_terminal(self, node: PlanNode, goal: str) -> None:
        """Execute a terminal node via the inner engine.

        Mutates ``node`` in place: sets status, result, error, model_used,
        cost_usd based on inner engine execution.
        """
        node.status = SubTaskStatus.RUNNING

        task = self._build_task(node, goal)
        try:
            result_task = await self._inner.execute(task)
        except Exception as exc:
            node.status = SubTaskStatus.FAILED
            node.error = str(exc)[:500]
            logger.warning(
                "NodeExecutor: inner engine raised for node '%s': %s",
                node.description,
                exc,
            )
            return

        self._apply_result(node, result_task)

    @staticmethod
    def to_subtask(node: PlanNode) -> SubTask:
        """Convert a PlanNode to a SubTask for inner engine consumption."""
        return SubTask(
            id=node.id,
            description=node.description,
            status=SubTaskStatus.PENDING,
            input_artifacts=dict(node.input_artifacts),
            output_artifacts=dict(node.output_artifacts),
            spawned_by_reflection=node.spawned_by_reflection,
        )

    @staticmethod
    def inject_artifacts(
        node: PlanNode,
        previous_nodes: list[PlanNode],
    ) -> None:
        """Chain artifacts: inject completed nodes' outputs into this node's inputs.

        For each previous node that has output_artifacts, merge them into
        this node's input_artifacts (existing keys are NOT overwritten).
        """
        for prev in previous_nodes:
            if prev.status != SubTaskStatus.SUCCESS:
                continue
            for key, value in prev.output_artifacts.items():
                if key not in node.input_artifacts:
                    node.input_artifacts[key] = value

    @staticmethod
    def _build_task(node: PlanNode, goal: str) -> TaskEntity:
        """Create a single-subtask TaskEntity for inner engine execution.

        The subtask description includes the parent goal for context.
        """
        description = node.description
        if node.input_artifacts:
            artifact_info = ", ".join(f"{k}: {v[:100]}" for k, v in node.input_artifacts.items())
            description = f"{description}\n\nAvailable context:\n{artifact_info}"

        # Classify complexity so inner engine picks the right execution path
        # (SIMPLE → direct LLM, MEDIUM+ → ReAct with tools)
        complexity = TaskComplexityClassifier.classify(description)

        subtask = SubTask(
            id=node.id,
            description=description,
            status=SubTaskStatus.PENDING,
            complexity=complexity,
            input_artifacts=dict(node.input_artifacts),
            output_artifacts=dict(node.output_artifacts),
        )
        # Include the full original goal so the inner engine retains entity context.
        # e.g. "Research Hikawa Shrine history" keeps "Hikawa Shrine" visible.
        return TaskEntity(
            goal=f"[Original goal: {goal}] Current step: {node.description}",
            status=TaskStatus.PENDING,
            subtasks=[subtask],
        )

    @staticmethod
    def _apply_result(node: PlanNode, result_task: TaskEntity) -> None:
        """Apply inner engine execution results back to the PlanNode."""
        if not result_task.subtasks:
            node.status = SubTaskStatus.FAILED
            node.error = "Inner engine returned no subtasks"
            return

        subtask = result_task.subtasks[0]
        node.status = subtask.status
        node.result = subtask.result
        node.error = subtask.error
        node.cost_usd = subtask.cost_usd

        if subtask.model_used:
            node.model_used = subtask.model_used
        if subtask.engine_used:
            node.model_used = subtask.engine_used

        # Merge output artifacts from executed subtask
        for key, value in subtask.output_artifacts.items():
            node.output_artifacts[key] = value
