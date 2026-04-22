"""FractalTaskEngine — recursive execution engine with dual evaluation gates
and reflection-driven dynamic node spawning (Living Fractal).

Sprint 15.5 (TD-103): Central integration point that wraps LangGraphTaskEngine.
Sprint 35  (TD-163): Reflection cycle — after visible nodes complete, assess
  goal satisfaction and dynamically spawn new sibling nodes as needed.
Sprint 36  (TD-167): SIMPLE task bypass — LLM intent analysis determines if a
  goal can skip fractal decomposition entirely for 4-6x faster execution.
Sprint 36.1 (TD-168): Gate 2 skip — successful terminal nodes skip result
  evaluation LLM call for ~30s latency savings per node.
Sprint 37  (TD-169): Parallel node execution — independent nodes in a plan
  execute simultaneously via asyncio.gather for 2-3x speedup.

Architecture (WRAP strategy):
  FractalTaskEngine (recursion + eval gates + candidate space + reflection)
      |
      +-- SIMPLE bypass -> LangGraphTaskEngine directly (~30s vs ~4.5min)
      +-- Terminal node execution -> LangGraphTaskEngine (EXISTING)

Key flows:
  decompose(goal) -> Planner -> Gate 1 -> SubTask[]
  execute(task)   -> bypass check (LLM intent analysis)
                  -> if SIMPLE: delegate to inner engine directly
                  -> else: recursive loop with Gate 2 evaluation per node
                  -> reflection cycle → spawn new nodes if unsatisfied
"""

from __future__ import annotations

import asyncio
import copy
import logging
import time
import uuid
from collections import deque
from typing import TYPE_CHECKING, Any

from domain.entities.fractal_engine import (
    CandidateNode,
    ExecutionPlan,
    PlanNode,
    ResultEvaluation,
)
from domain.entities.task import SubTask, TaskEntity
from domain.ports.fractal_learning_repository import FractalLearningRepository
from domain.ports.plan_evaluator import PlanEvaluatorPort
from domain.ports.planner import PlannerPort
from domain.ports.reflection_evaluator import ReflectionEvaluatorPort
from domain.ports.result_evaluator import ResultEvaluatorPort
from domain.ports.task_engine import TaskEngine
from domain.services.candidate_space_manager import CandidateSpaceManager
from domain.services.failure_propagator import FailurePropagator
from domain.services.fractal_learner import FractalLearner
from domain.services.nesting_depth_controller import NestingDepthController
from domain.value_objects.fractal_engine import (
    NodeState,
    PlanEvalDecision,
    ResultEvalDecision,
)
from domain.value_objects.output_requirement import OutputRequirement
from domain.value_objects.status import PlanStatus, SubTaskStatus, TaskStatus
from domain.value_objects.task_complexity import TaskComplexity
from infrastructure.fractal.node_executor import NodeExecutor

if TYPE_CHECKING:
    from domain.ports.task_repository import TaskRepository
    from domain.services.output_requirement_classifier import OutputRequirementClassifier
    from infrastructure.fractal.bypass_classifier import FractalBypassClassifier

logger = logging.getLogger(__name__)


class _PlanFailureError(Exception):
    """Raised when a plan cannot be completed at the current nesting level.

    Carries a feedback message for the parent level to use in replanning.
    """

    def __init__(self, feedback: str) -> None:
        self.feedback = feedback
        super().__init__(feedback)


class FractalTaskEngine(TaskEngine):
    """Recursive fractal execution engine with dual evaluation gates
    and reflection-driven dynamic node spawning.

    Wraps an inner TaskEngine (LangGraphTaskEngine) for terminal node
    execution. Non-terminal nodes are recursively decomposed and executed
    by spawning child engine instances at nesting_level + 1.

    After all visible nodes complete, a reflection cycle assesses whether
    the goal is fully addressed. If not, new sibling nodes are dynamically
    spawned — making the task graph "alive" and self-expanding.
    """

    def __init__(
        self,
        planner: PlannerPort,
        plan_evaluator: PlanEvaluatorPort,
        result_evaluator: ResultEvaluatorPort,
        inner_engine: TaskEngine,
        *,
        max_depth: int = 3,
        max_retries: int = 3,
        max_plan_attempts: int = 2,
        plan_eval_min_score: float = 0.5,
        result_eval_ok_threshold: float = 0.7,
        result_eval_retry_threshold: float = 0.4,
        budget_usd: float = 0.0,
        learning_repo: FractalLearningRepository | None = None,
        reflection_evaluator: ReflectionEvaluatorPort | None = None,
        max_reflection_rounds: int = 2,
        max_total_nodes: int = 20,
        bypass_classifier: FractalBypassClassifier | None = None,
        skip_gate2_for_terminal_success: bool = False,
        parallel_node_execution: bool = False,
        skip_reflection_for_single_success: bool = False,
        cache_planner_candidates: bool = False,
        max_concurrent_nodes: int = 0,
        throttle_delay_ms: int = 0,
        output_classifier: OutputRequirementClassifier | None = None,
        max_execution_seconds: int = 180,
    ) -> None:
        self._planner = planner
        self._plan_evaluator = plan_evaluator
        self._result_evaluator = result_evaluator
        self._inner = inner_engine
        self._node_executor = NodeExecutor(inner_engine)

        self._max_depth = max_depth
        self._max_retries = max_retries
        self._max_plan_attempts = max_plan_attempts
        self._plan_eval_min_score = plan_eval_min_score
        self._result_eval_ok_threshold = result_eval_ok_threshold
        self._result_eval_retry_threshold = result_eval_retry_threshold
        self._budget_usd = budget_usd
        self._learning_repo = learning_repo

        # Living Fractal: reflection-driven dynamic node spawning (TD-163)
        self._reflection_evaluator = reflection_evaluator
        self._max_reflection_rounds = max_reflection_rounds
        self._max_total_nodes = max_total_nodes

        # SIMPLE task bypass: skip fractal for trivial goals (TD-167)
        self._bypass_classifier = bypass_classifier

        # Gate 2 skip: when True, successful terminal nodes skip result
        # evaluation LLM call for ~30s latency savings (TD-168)
        self._skip_gate2_for_terminal_success = skip_gate2_for_terminal_success

        # Parallel node execution: when True, independent nodes in a batch
        # execute simultaneously via asyncio.gather (TD-169)
        self._parallel_node_execution = parallel_node_execution

        # Reflection skip: when True, single-node successful plans skip
        # the reflection LLM call for ~30s savings (TD-171)
        self._skip_reflection_for_single_success = skip_reflection_for_single_success

        # Planner candidate caching: when True, cache generate_candidates
        # results keyed by goal+nesting_level to skip LLM call on repeat
        # submissions (TD-173)
        self._cache_planner_candidates = cache_planner_candidates
        self._plan_cache: dict[str, list[CandidateNode]] = {}

        # Concurrency throttle: limit parallel node execution (TD-175)
        self._max_concurrent_nodes = max_concurrent_nodes  # 0 = unlimited
        self._throttle_delay_ms = throttle_delay_ms

        # Output-aware evaluation: classifier for goal output requirements
        self._output_classifier = output_classifier

        # TD-181: Time-based timeout — hard limit to prevent zombie tasks.
        # Kills execution after max_execution_seconds regardless of retries/reflection.
        self._max_execution_seconds = max_execution_seconds
        self._execution_start: float = 0.0

        # Per-execution overrides set via set_execution_overrides() (TD-175)
        self._pending_overrides: dict[str, int] = {}

        # Per-execution state (set in execute(), cleared in finally)
        self._exec_semaphore: asyncio.Semaphore | None = None
        self._exec_throttle_delay: int = 0
        self._exec_max_depth: int = max_depth

        # SSE event bus + task repo — wired externally by ExecuteTaskUseCase
        self._event_bus: Any | None = None
        self._task_repo: TaskRepository | None = None
        self._task: TaskEntity | None = None

    # ------------------------------------------------------------------
    # Per-task override support (TD-175)
    # ------------------------------------------------------------------

    def set_execution_overrides(self, overrides: dict[str, int]) -> None:
        """Set per-task fractal overrides consumed by the next execute() call.

        Supported keys: max_depth, max_concurrent_nodes, throttle_delay_ms.
        """
        self._pending_overrides = dict(overrides)

    def _apply_execution_overrides(self) -> None:
        """Read pending overrides and set per-execution state."""
        overrides = self._pending_overrides
        self._pending_overrides = {}

        max_conc = overrides.get(
            "max_concurrent_nodes", self._max_concurrent_nodes
        )
        self._exec_semaphore = (
            asyncio.Semaphore(max_conc) if max_conc > 0 else None
        )
        self._exec_throttle_delay = overrides.get(
            "throttle_delay_ms", self._throttle_delay_ms
        )
        self._exec_max_depth = overrides.get("max_depth", self._max_depth)

        if self._exec_semaphore or self._exec_throttle_delay:
            logger.info(
                "Fractal throttle: concurrent=%s delay=%dms depth=%d",
                max_conc or "unlimited",
                self._exec_throttle_delay,
                self._exec_max_depth,
            )

    # ------------------------------------------------------------------
    # SSE event helpers
    # ------------------------------------------------------------------

    def _emit(self, event_type: str, **data: object) -> None:
        """Push an SSE event if event_bus is wired."""
        if self._event_bus is not None and self._task is not None:
            self._event_bus.publish(self._task.id, {"type": event_type, **data})

    async def _persist_intermediate(self) -> None:
        """Write current task state to DB so page-refresh sees updates."""
        if self._task_repo is not None and self._task is not None:
            try:
                self._task.total_cost_usd = sum(s.cost_usd for s in self._task.subtasks)
                await self._task_repo.update(self._task)
            except Exception:
                logger.debug("Intermediate persist failed — non-fatal", exc_info=True)

    def _is_timed_out(self) -> bool:
        """TD-181: Check whether execution has exceeded the time limit."""
        if self._max_execution_seconds <= 0 or self._execution_start <= 0:
            return False
        return (time.monotonic() - self._execution_start) > self._max_execution_seconds

    def _sync_subtask(self, node: PlanNode) -> None:
        """Update the SubTask in self._task that corresponds to this PlanNode."""
        if self._task is None:
            return
        for st in self._task.subtasks:
            if st.id == node.id:
                st.status = node.status
                st.result = node.result
                st.error = node.error
                st.model_used = node.model_used
                st.cost_usd = node.cost_usd
                st.output_artifacts = dict(node.output_artifacts)
                return

    # ------------------------------------------------------------------
    # TaskEngine interface
    # ------------------------------------------------------------------

    async def decompose(self, goal: str) -> list[SubTask]:
        """Return a lightweight placeholder — real planning happens in execute().

        FractalTaskEngine.execute() re-plans from task.goal using recursive
        decomposition, so running the full Planner + Gate ① pipeline here
        would double the cost with the result discarded (TD-107).
        """
        return [SubTask(description=goal)]

    async def execute(self, task: TaskEntity) -> TaskEntity:
        """Execute a task using recursive fractal decomposition with
        reflection-driven dynamic node spawning.

        TD-167: If bypass classifier determines the goal is SIMPLE, delegates
        directly to inner engine (LangGraph) — skipping plan/eval/reflection
        for ~4-6x faster execution on trivial tasks.

        Re-plans from task.goal rather than using pre-existing subtasks.
        Emits SSE events for real-time UI updates when event_bus is wired.
        """
        self._task = task
        task.status = TaskStatus.RUNNING
        self._execution_start = time.monotonic()

        # TD-175: Apply per-execution concurrency/throttle overrides
        self._apply_execution_overrides()

        # TD-167: SIMPLE task bypass — LLM intent analysis
        if self._bypass_classifier is not None:
            try:
                decision = await self._bypass_classifier.should_bypass(task.goal)
                logger.info(
                    "Bypass classifier: bypass=%s complexity=%s reason=%r",
                    decision.bypass,
                    decision.complexity.value,
                    decision.reason[:100],
                )
                if decision.bypass:
                    return await self._execute_bypass(task)
            except Exception:
                logger.warning(
                    "Bypass classification error — falling through to fractal",
                    exc_info=True,
                )

        try:
            # Classify output requirement for the top-level goal so Gate ②
            # can check whether the right kind of output was produced.
            goal_output_req: OutputRequirement | None = None
            if self._output_classifier is not None:
                try:
                    goal_output_req = await self._output_classifier.classify(task.goal)
                    logger.info(
                        "Output requirement for goal: %s", goal_output_req.value
                    )
                except Exception:
                    logger.warning(
                        "Output requirement classification failed — skipping",
                        exc_info=True,
                    )

            plan = await self._generate_approved_plan(task.goal, nesting_level=0)

            # Propagate output requirement to all terminal visible nodes
            if goal_output_req is not None:
                for node in plan.visible_nodes:
                    if node.is_terminal:
                        node.output_requirement = goal_output_req

            # Convert initial visible nodes to SubTasks immediately for SSE
            task.subtasks = [NodeExecutor.to_subtask(n) for n in plan.visible_nodes]
            self._emit(
                "task_started",
                status="running",
                subtask_count=len(task.subtasks),
                subtasks=[
                    {"id": s.id, "description": s.description, "dependencies": s.dependencies}
                    for s in task.subtasks
                ],
            )
            await self._persist_intermediate()

            # Execute with reflection cycle
            # TD-181: Wrap with asyncio.wait_for for hard timeout.
            # Cooperative checks inside _execute_plan handle graceful shutdown,
            # but asyncio.wait_for is the last resort when inner engine hangs.
            timeout = (
                float(self._max_execution_seconds)
                if self._max_execution_seconds > 0
                else None
            )
            try:
                completed_nodes, total_cost = await asyncio.wait_for(
                    self._execute_plan(plan, task.goal, nesting_level=0),
                    timeout=timeout,
                )
            except TimeoutError:
                elapsed = time.monotonic() - self._execution_start
                logger.error(
                    "FractalTaskEngine HARD TIMEOUT after %.0fs (limit=%ds)",
                    elapsed,
                    self._max_execution_seconds,
                )
                task.status = TaskStatus.FAILED
                for st in task.subtasks:
                    if st.status in (SubTaskStatus.RUNNING, SubTaskStatus.PENDING):
                        st.status = SubTaskStatus.FAILED
                        st.error = f"Hard timeout after {elapsed:.0f}s"
                await self._persist_intermediate()
                return task

            # Final sync: ensure all SubTask states match completed PlanNodes
            for node in completed_nodes:
                self._sync_subtask(node)

            task.total_cost_usd = total_cost
            all_ok = all(
                n.status in (SubTaskStatus.SUCCESS, SubTaskStatus.DEGRADED)
                for n in completed_nodes
            )
            task.status = TaskStatus.SUCCESS if all_ok else TaskStatus.FAILED

            # TD-181: Catch any subtasks still stuck in RUNNING after timeout
            for st in task.subtasks:
                if st.status in (SubTaskStatus.RUNNING, SubTaskStatus.PENDING):
                    st.status = SubTaskStatus.FAILED
                    st.error = st.error or "Execution did not complete"

            # Build consolidated final answer from successful nodes (TD-174)
            successful_results = [
                n.result for n in completed_nodes
                if n.status in (SubTaskStatus.SUCCESS, SubTaskStatus.DEGRADED)
                and n.result
            ]
            if successful_results:
                task.final_answer = "\n\n---\n\n".join(successful_results)

            # Learning hook: record patterns from execution
            await self._record_learning(task.goal, completed_nodes)

        except _PlanFailureError as e:
            task.status = TaskStatus.FAILED
            if not task.subtasks:
                task.subtasks = [
                    SubTask(
                        description=f"Planning failed: {e.feedback}",
                        status=SubTaskStatus.FAILED,
                        error=e.feedback,
                    )
                ]
        except Exception as e:
            logger.exception("FractalTaskEngine.execute failed: %s", e)
            task.status = TaskStatus.FAILED
        finally:
            self._task = None
            self._exec_semaphore = None
            self._exec_throttle_delay = 0
            self._exec_max_depth = self._max_depth

        return task

    # ------------------------------------------------------------------
    # SIMPLE task bypass (TD-167)
    # ------------------------------------------------------------------

    async def _execute_bypass(self, task: TaskEntity) -> TaskEntity:
        """Fast-path for SIMPLE tasks: skip fractal planning entirely.

        Creates a single SubTask with SIMPLE complexity and delegates to the
        inner engine (LangGraph), which will use the direct-LLM path.
        Wires SSE event bus and task repo so the inner engine emits events.
        """
        logger.info("SIMPLE bypass: delegating '%s' to inner engine", task.goal[:80])

        # Create a single SIMPLE subtask wrapping the full goal
        subtask = SubTask(
            description=task.goal,
            status=SubTaskStatus.PENDING,
            complexity=TaskComplexity.SIMPLE,
        )
        task.subtasks = [subtask]

        # Wire inner engine for SSE events + persistence
        inner_had_bus = getattr(self._inner, "_event_bus", None)
        inner_had_repo = getattr(self._inner, "_task_repo", None)
        try:
            if hasattr(self._inner, "_event_bus"):
                self._inner._event_bus = self._event_bus
            if hasattr(self._inner, "_task_repo"):
                self._inner._task_repo = self._task_repo

            result = await self._inner.execute(task)
            # Set final_answer from bypass result (TD-174)
            successful = [
                s.result for s in result.subtasks
                if s.status == SubTaskStatus.SUCCESS and s.result
            ]
            if successful:
                result.final_answer = successful[0]
            return result
        except Exception as exc:
            logger.exception("SIMPLE bypass inner engine failed: %s", exc)
            task.status = TaskStatus.FAILED
            if task.subtasks:
                task.subtasks[0].status = SubTaskStatus.FAILED
                task.subtasks[0].error = str(exc)[:500]
            return task
        finally:
            # Unwire inner engine to avoid side effects on subsequent calls
            if hasattr(self._inner, "_event_bus"):
                self._inner._event_bus = inner_had_bus
            if hasattr(self._inner, "_task_repo"):
                self._inner._task_repo = inner_had_repo
            self._task = None

    # ------------------------------------------------------------------
    # Planning: generate + evaluate + approve
    # ------------------------------------------------------------------

    async def _generate_approved_plan(
        self,
        goal: str,
        nesting_level: int,
        context: str = "",
    ) -> ExecutionPlan:
        """Generate candidates via Planner, evaluate via Gate 1.

        Retries up to max_plan_attempts if Gate 1 rejects.
        Raises _PlanFailureError if all attempts fail.
        """
        feedback = ""
        for attempt in range(self._max_plan_attempts):
            plan_context = context
            if feedback:
                plan_context = f"{context}\nPrevious attempt rejected: {feedback}"

            # Check planner cache (TD-173): only on first attempt (no feedback)
            cache_key = f"{goal}::{nesting_level}"
            cached = (
                self._cache_planner_candidates
                and not feedback
                and cache_key in self._plan_cache
            )

            if cached:
                candidates = copy.deepcopy(self._plan_cache[cache_key])
                logger.debug(
                    "Planner cache hit for '%s' (nesting=%d)",
                    goal[:60],
                    nesting_level,
                )
            else:
                candidates = await self._planner.generate_candidates(
                    goal=goal,
                    context=plan_context,
                    nesting_level=nesting_level,
                )
                # Store in cache on successful generation (TD-173)
                if self._cache_planner_candidates and candidates and not feedback:
                    self._plan_cache[cache_key] = copy.deepcopy(candidates)

            if not candidates:
                feedback = "Planner returned no candidates"
                logger.warning(
                    "Plan attempt %d/%d: no candidates for '%s'",
                    attempt + 1,
                    self._max_plan_attempts,
                    goal[:80],
                )
                continue

            plan = self._build_plan(goal, nesting_level, candidates)

            # Gate 1: Plan evaluation
            evaluation = await self._plan_evaluator.evaluate(plan, goal)

            if evaluation.decision == PlanEvalDecision.APPROVED:
                # Apply evaluation to prune low-scoring candidates
                CandidateSpaceManager.apply_evaluation(
                    plan.candidate_space,
                    evaluation,
                    min_score=self._plan_eval_min_score,
                )
                # Rebuild visible_nodes from remaining VISIBLE candidates
                plan.visible_nodes = [
                    c.node for c in plan.candidate_space if c.state == NodeState.VISIBLE
                ]
                plan.status = PlanStatus.APPROVED
                logger.info(
                    "Plan approved (attempt %d): %d visible nodes, score=%.2f",
                    attempt + 1,
                    len(plan.visible_nodes),
                    evaluation.overall_score,
                )
                return plan

            # Rejected — collect feedback for next attempt
            feedback = evaluation.feedback or "Plan did not meet quality threshold"
            logger.info(
                "Plan rejected (attempt %d/%d): %s",
                attempt + 1,
                self._max_plan_attempts,
                feedback[:200],
            )

        raise _PlanFailureError(
            f"All {self._max_plan_attempts} plan attempts rejected. Last feedback: {feedback}"
        )

    def _build_plan(
        self,
        goal: str,
        nesting_level: int,
        candidates: list[CandidateNode],
    ) -> ExecutionPlan:
        """Build an ExecutionPlan from candidates.

        Visible candidates become visible_nodes, all go to candidate_space.
        """
        visible_nodes = [c.node for c in candidates if c.state == NodeState.VISIBLE]
        return ExecutionPlan(
            id=str(uuid.uuid4()),
            goal=goal,
            nesting_level=nesting_level,
            visible_nodes=visible_nodes,
            candidate_space=list(candidates),
            status=PlanStatus.PROPOSED,
        )

    # ------------------------------------------------------------------
    # Execution: dynamic queue with Gate 2 + reflection cycle
    # ------------------------------------------------------------------

    async def _execute_plan(
        self,
        plan: ExecutionPlan,
        goal: str,
        nesting_level: int,
    ) -> tuple[list[PlanNode], float]:
        """Execute visible nodes with Gate 2 evaluation and reflection cycle.

        TD-169: Independent nodes in each batch execute in parallel via
        asyncio.gather for 2-3x speedup on multi-node plans.

        After all pending nodes are executed, the reflection evaluator checks
        goal satisfaction. If unsatisfied, new nodes are spawned for the next
        batch.

        Returns (completed_nodes, total_cost_usd).
        Raises _PlanFailureError if unrecoverable failure occurs.
        """
        plan.status = PlanStatus.EXECUTING
        completed: list[PlanNode] = []
        pending: deque[PlanNode] = deque(plan.visible_nodes)
        total_cost = 0.0

        while pending:
            # TD-181: Time-based timeout — hard kill to prevent zombie tasks
            if self._is_timed_out():
                elapsed = time.monotonic() - self._execution_start
                logger.warning(
                    "Fractal execution timed out after %.0fs (limit=%ds). "
                    "Marking %d remaining nodes as FAILED.",
                    elapsed, self._max_execution_seconds, len(pending),
                )
                for node in pending:
                    node.status = SubTaskStatus.FAILED
                    node.error = f"Execution timed out after {elapsed:.0f}s"
                    completed.append(node)
                    self._sync_subtask(node)
                pending.clear()
                break

            # Drain all pending nodes into a batch for parallel execution
            batch: list[PlanNode] = []
            while pending:
                batch.append(pending.popleft())

            # Pre-flight: setup each node (retries, status, SSE, artifacts, budget)
            for node in batch:
                node.max_retries = self._max_retries
                if self._task is not None:
                    for st in self._task.subtasks:
                        if st.id == node.id:
                            st.status = SubTaskStatus.RUNNING
                            break
                self._emit(
                    "subtask_started",
                    subtask_id=node.id,
                    description=node.description,
                    dependencies=[],
                )
                NodeExecutor.inject_artifacts(node, completed)
                within_budget, reason = NestingDepthController.check_budget(
                    total_cost, self._budget_usd
                )
                if not within_budget:
                    logger.warning(
                        "Budget exhausted (%s), forcing terminal", reason
                    )
                    node.is_terminal = True

            await self._persist_intermediate()

            # Execute: parallel or sequential based on configuration
            use_parallel = (
                self._parallel_node_execution
                and len(batch) > 1
            )

            if use_parallel:
                logger.info(
                    "Parallel execution: %d nodes in batch", len(batch)
                )
                errors = list(
                    await asyncio.gather(
                        *(
                            self._execute_node_safe(
                                n, goal, nesting_level, total_cost
                            )
                            for n in batch
                        ),
                    )
                )
            else:
                # Sequential execution — mirrors original per-node loop
                for node in batch:
                    # Budget check between sequential nodes
                    within_budget, reason = (
                        NestingDepthController.check_budget(
                            total_cost, self._budget_usd
                        )
                    )
                    if not within_budget:
                        logger.warning(
                            "Budget exhausted (%s), forcing terminal",
                            reason,
                        )
                        node.is_terminal = True

                    # Re-inject artifacts (may have new outputs from
                    # previous nodes in this batch)
                    NodeExecutor.inject_artifacts(node, completed)

                    err = await self._execute_node_safe(
                        node, goal, nesting_level, total_cost
                    )

                    if isinstance(err, _PlanFailureError):
                        fb_node = await self._try_fallback(
                            node, err, plan, goal, nesting_level,
                            total_cost, completed,
                        )
                        if fb_node is not None:
                            completed.append(fb_node)
                            total_cost += fb_node.cost_usd
                            self._sync_subtask(fb_node)
                            self._emit(
                                "subtask_completed",
                                subtask_id=fb_node.id,
                                status=fb_node.status.value,
                                result=(fb_node.result or "")[:500],
                                model_used=fb_node.model_used,
                                cost_usd=fb_node.cost_usd,
                                error=fb_node.error,
                            )
                            continue  # Skip adding original failed node

                    completed.append(node)
                    total_cost += node.cost_usd
                    self._sync_subtask(node)
                    self._emit(
                        "subtask_completed",
                        subtask_id=node.id,
                        status=node.status.value,
                        result=(node.result or "")[:500],
                        model_used=node.model_used,
                        cost_usd=node.cost_usd,
                        error=node.error,
                    )

                await self._persist_intermediate()
                if not pending:
                    new_nodes = await self._maybe_reflect(
                        plan, goal, nesting_level, completed, total_cost
                    )
                    for n in new_nodes:
                        pending.append(n)
                continue

            # Post-flight: handle results, fallbacks, cost tracking
            for node, error in zip(batch, errors, strict=True):
                if isinstance(error, _PlanFailureError):
                    fb_node = await self._try_fallback(
                        node, error, plan, goal, nesting_level,
                        total_cost, completed,
                    )
                    if fb_node is not None:
                        # Fallback replaced failed node
                        completed.append(fb_node)
                        total_cost += fb_node.cost_usd
                        self._sync_subtask(fb_node)
                        self._emit(
                            "subtask_completed",
                            subtask_id=fb_node.id,
                            status=fb_node.status.value,
                            result=(fb_node.result or "")[:500],
                            model_used=fb_node.model_used,
                            cost_usd=fb_node.cost_usd,
                            error=fb_node.error,
                        )
                        continue

                completed.append(node)
                total_cost += node.cost_usd
                self._sync_subtask(node)
                self._emit(
                    "subtask_completed",
                    subtask_id=node.id,
                    status=node.status.value,
                    result=(node.result or "")[:500],
                    model_used=node.model_used,
                    cost_usd=node.cost_usd,
                    error=node.error,
                )

            await self._persist_intermediate()

            # Reflection cycle: when queue empty, check goal satisfaction
            if not pending:
                new_nodes = await self._maybe_reflect(
                    plan, goal, nesting_level, completed, total_cost
                )
                for n in new_nodes:
                    pending.append(n)

        plan.status = PlanStatus.COMPLETED
        return completed, total_cost

    async def _execute_node_safe(
        self,
        node: PlanNode,
        goal: str,
        nesting_level: int,
        accumulated_cost: float,
    ) -> _PlanFailureError | None:
        """Execute a single node, returning the error instead of raising.

        This wrapper enables asyncio.gather to run multiple nodes in parallel
        without one failure aborting the entire batch.

        TD-175: Uses per-execution semaphore to limit concurrency and applies
        throttle delay after completion to smooth CPU load.
        """
        try:
            if self._exec_semaphore is not None:
                async with self._exec_semaphore:
                    await self._execute_with_eval(
                        node, goal, nesting_level, accumulated_cost
                    )
                    # Throttle delay inside semaphore so next node waits (TD-175)
                    if self._exec_throttle_delay > 0:
                        await asyncio.sleep(self._exec_throttle_delay / 1000)
            else:
                await self._execute_with_eval(
                    node, goal, nesting_level, accumulated_cost
                )
                # Throttle delay between node completions (TD-175)
                if self._exec_throttle_delay > 0:
                    await asyncio.sleep(self._exec_throttle_delay / 1000)

            return None
        except _PlanFailureError as pf:
            return pf
        except Exception as exc:
            # TD-180: Catch-all — ensure node never stays RUNNING on unexpected errors
            node.status = SubTaskStatus.FAILED
            node.error = f"Unexpected error: {exc!s}"[:500]
            logger.error(
                "Node '%s' failed with unexpected error: %s",
                node.description[:60], exc,
            )
            return None  # Don't propagate — treat as local failure

    async def _try_fallback(
        self,
        node: PlanNode,
        pf: _PlanFailureError,
        plan: ExecutionPlan,
        goal: str,
        nesting_level: int,
        total_cost: float,
        completed: list[PlanNode],
    ) -> PlanNode | None:
        """Try conditional fallbacks for a failed node.

        Returns the fallback node if one was activated and executed,
        or None if no fallback was available (original node marked as FAILED).
        """
        has_fallbacks = bool(
            CandidateSpaceManager.get_fallback_candidates(plan.candidate_space)
        )
        FailurePropagator.create_report(
            node,
            ResultEvaluation(
                node_id=node.id,
                decision=ResultEvalDecision.REPLAN,
                feedback=pf.feedback,
                overall_score=0.0,
            ),
            retries_exhausted=True,
        )
        if has_fallbacks:
            activated = CandidateSpaceManager.activate_conditional(
                plan.candidate_space,
                f"failure:{node.description}",
            )
            if activated:
                logger.info(
                    "Activated %d fallback(s) for failed node '%s'",
                    len(activated),
                    node.description,
                )
                fb_node = activated[0].node
                fb_node.max_retries = self._max_retries
                NodeExecutor.inject_artifacts(fb_node, completed)
                if self._task is not None:
                    self._task.subtasks = [
                        st for st in self._task.subtasks
                        if st.id != node.id
                    ]
                    self._task.subtasks.append(
                        NodeExecutor.to_subtask(fb_node)
                    )
                try:
                    await self._execute_with_eval(
                        fb_node, goal, nesting_level, total_cost
                    )
                except _PlanFailureError:
                    fb_node.status = SubTaskStatus.FAILED
                return fb_node

        node.status = SubTaskStatus.FAILED
        if not node.error:
            node.error = pf.feedback
        return None

    async def _maybe_reflect(
        self,
        plan: ExecutionPlan,
        goal: str,
        nesting_level: int,
        completed: list[PlanNode],
        total_cost: float,
    ) -> list[PlanNode]:
        """Run one reflection cycle if allowed. Returns new nodes to execute."""
        # TD-181: No reflection after timeout
        if self._is_timed_out():
            return []
        if self._reflection_evaluator is None:
            return []

        # Only reflect at nesting level 0 (top-level plan) for now
        if nesting_level > 0:
            return []

        # TD-171: Skip reflection for single-node plans where the node
        # succeeded. Opt-in via skip_reflection_for_single_success.
        if (
            self._skip_reflection_for_single_success
            and len(completed) == 1
            and completed[0].status == SubTaskStatus.SUCCESS
            and plan.reflection_rounds == 0
        ):
            logger.debug(
                "Reflection skipped: single-node success for '%s'",
                goal[:60],
            )
            return []

        allowed, reason = NestingDepthController.check_reflection_allowed(
            plan.reflection_rounds,
            self._max_reflection_rounds,
            len(completed),
            self._max_total_nodes,
            total_cost,
            self._budget_usd,
        )
        if not allowed:
            logger.debug("Reflection skipped: %s", reason)
            return []

        self._emit("reflection_started", round=plan.reflection_rounds + 1)

        try:
            reflection = await self._reflection_evaluator.reflect(
                goal, completed, nesting_level
            )
        except Exception:
            logger.warning("Reflection evaluator failed — skipping", exc_info=True)
            self._emit(
                "reflection_complete", satisfied=True, spawned_count=0
            )
            return []

        if reflection.is_satisfied or not reflection.suggested_descriptions:
            logger.info(
                "Reflection satisfied (round %d, confidence=%.2f): %s",
                plan.reflection_rounds + 1,
                reflection.confidence,
                reflection.feedback[:200],
            )
            self._emit(
                "reflection_complete", satisfied=True, spawned_count=0
            )
            return []

        # Spawn new nodes from reflection suggestions
        new_nodes = self._create_reflection_nodes(
            reflection.suggested_descriptions,
            nesting_level,
            plan,
        )

        plan.reflection_rounds += 1

        logger.info(
            "Reflection round %d: spawning %d new node(s) — %s",
            plan.reflection_rounds,
            len(new_nodes),
            ", ".join(n.description[:50] for n in new_nodes),
        )

        # Add new nodes as SubTasks to the live task + emit SSE events
        if self._task is not None:
            for node in new_nodes:
                subtask = NodeExecutor.to_subtask(node)
                subtask.reflection_round = plan.reflection_rounds
                self._task.subtasks.append(subtask)
                self._emit(
                    "node_spawned",
                    subtask_id=node.id,
                    description=node.description,
                    spawned_by="reflection",
                    reflection_round=plan.reflection_rounds,
                )
            await self._persist_intermediate()

        self._emit(
            "reflection_complete",
            satisfied=False,
            spawned_count=len(new_nodes),
        )

        return new_nodes

    @staticmethod
    def _create_reflection_nodes(
        descriptions: list[str],
        nesting_level: int,
        plan: ExecutionPlan,
    ) -> list[PlanNode]:
        """Create PlanNode objects from reflection suggestions."""
        nodes: list[PlanNode] = []
        for desc in descriptions:
            node = PlanNode(
                id=str(uuid.uuid4())[:8],
                description=desc,
                nesting_level=nesting_level,
                is_terminal=True,  # Reflection nodes are terminal by default
                spawned_by_reflection=True,
            )
            nodes.append(node)
            # Add to candidate space as VISIBLE for tracking
            plan.candidate_space.append(
                CandidateNode(
                    node=node,
                    state=NodeState.VISIBLE,
                    score=0.5,
                )
            )
            plan.visible_nodes.append(node)
        return nodes

    async def _execute_with_eval(
        self,
        node: PlanNode,
        goal: str,
        nesting_level: int,
        accumulated_cost: float,
    ) -> None:
        """Execute a single node with Gate 2 evaluation and retry logic.

        TD-168: Terminal nodes that succeed via the inner engine skip Gate 2.
        The inner engine already validates results; re-evaluating successful
        terminal nodes adds ~30s of LLM latency with no actionable benefit.

        Mutates ``node`` in place. May raise _PlanFailureError if failure
        must propagate to parent level.
        """
        should_term, reason = NestingDepthController.should_terminate(
            nesting_level, node.is_terminal, max_depth=self._exec_max_depth
        )

        while True:
            # TD-181: Abort retry loop if execution timed out
            if self._is_timed_out():
                node.status = SubTaskStatus.FAILED
                elapsed = time.monotonic() - self._execution_start
                node.error = f"Execution timed out after {elapsed:.0f}s"
                return

            if should_term:
                await self._node_executor.execute_terminal(node, goal)
            else:
                await self._execute_expandable(node, goal, nesting_level, accumulated_cost)

            # TD-168: Skip Gate 2 for successful terminal nodes.
            # The inner engine (LangGraph) already validated the result.
            # Saves ~30s of LLM evaluation latency per terminal node.
            # Opt-in via skip_gate2_for_terminal_success constructor param.
            if (
                self._skip_gate2_for_terminal_success
                and should_term
                and node.status == SubTaskStatus.SUCCESS
                and node.result
            ):
                logger.debug(
                    "Gate 2 skipped for successful terminal node '%s'",
                    node.description[:60],
                )
                return

            # Gate 2: Result evaluation (failed or non-terminal nodes)
            result_text = node.result or node.error or ""
            evaluation = await self._result_evaluator.evaluate(node, goal, result_text)

            if evaluation.decision == ResultEvalDecision.OK:
                node.status = SubTaskStatus.SUCCESS
                return

            if evaluation.decision == ResultEvalDecision.RETRY and node.can_retry:
                node.retry_count += 1
                node.status = SubTaskStatus.PENDING
                logger.info(
                    "Retrying node '%s' (attempt %d/%d): %s",
                    node.description,
                    node.retry_count,
                    node.max_retries,
                    evaluation.feedback[:200],
                )
                continue

            # REPLAN or retries exhausted — propagate to parent level
            retries_exhausted = not node.can_retry
            if FailurePropagator.should_propagate(evaluation, retries_exhausted):
                node.status = SubTaskStatus.FAILED
                node.error = evaluation.feedback
                raise _PlanFailureError(
                    f"Node '{node.description}' failed: {evaluation.feedback}"
                )

            # Mark failed but not propagated (e.g. RETRY with retries left)
            node.status = SubTaskStatus.FAILED
            node.error = evaluation.feedback
            return

    async def _execute_expandable(
        self,
        node: PlanNode,
        parent_goal: str,
        nesting_level: int,
        accumulated_cost: float,
    ) -> None:
        """Expand a non-terminal node into a sub-plan and execute recursively.

        The node's description becomes the sub-goal for the child engine.
        """
        child_level = nesting_level + 1
        node.status = SubTaskStatus.RUNNING
        sub_goal = node.description

        try:
            sub_plan = await self._generate_approved_plan(
                sub_goal,
                nesting_level=child_level,
                context=f"Parent goal: {parent_goal}",
            )

            # Expose child nodes to UI via task.subtasks + SSE (TD-174)
            if self._task is not None:
                for child_node in sub_plan.visible_nodes:
                    child_st = NodeExecutor.to_subtask(child_node)
                    child_st.dependencies = [node.id]
                    self._task.subtasks.append(child_st)
                    self._emit(
                        "node_spawned",
                        subtask_id=child_node.id,
                        description=child_node.description,
                        spawned_by="expansion",
                        parent_id=node.id,
                    )
                await self._persist_intermediate()

            child_nodes, child_cost = await self._execute_plan(
                sub_plan, sub_goal, nesting_level=child_level
            )

            node.cost_usd = child_cost

            # Aggregate child results
            all_ok = all(
                n.status in (SubTaskStatus.SUCCESS, SubTaskStatus.DEGRADED)
                for n in child_nodes
            )
            if all_ok:
                results = [n.result for n in child_nodes if n.result]
                node.result = "\n".join(results) if results else "Completed"
                node.status = SubTaskStatus.SUCCESS
            else:
                failures = [
                    f"{n.description}: {n.error}"
                    for n in child_nodes
                    if n.status == SubTaskStatus.FAILED
                ]
                node.error = "; ".join(failures) if failures else "Child nodes failed"
                node.status = SubTaskStatus.FAILED

            # Merge child output artifacts
            for child in child_nodes:
                for key, value in child.output_artifacts.items():
                    node.output_artifacts[key] = value

        except _PlanFailureError as e:
            node.status = SubTaskStatus.FAILED
            node.error = e.feedback
            raise

    # ------------------------------------------------------------------
    # Learning hooks
    # ------------------------------------------------------------------

    async def _record_learning(self, goal: str, nodes: list[PlanNode]) -> None:
        """Record error patterns and successful paths after execution.

        Fire-and-forget: never blocks task execution on learning failure.
        """
        if self._learning_repo is None:
            return

        try:
            # Record error patterns from failed nodes
            error_patterns = FractalLearner.extract_error_patterns(goal, nodes)
            for pattern in error_patterns:
                await self._learning_repo.save_error_pattern(pattern)

            # Record successful path if all nodes succeeded
            success_path = FractalLearner.extract_successful_path(goal, nodes)
            if success_path is not None:
                await self._learning_repo.save_successful_path(success_path)

            if error_patterns or success_path:
                logger.info(
                    "Learning recorded: %d error patterns, %s successful path",
                    len(error_patterns),
                    "1" if success_path else "0",
                )
        except Exception:
            logger.warning("Failed to record learning data", exc_info=True)
