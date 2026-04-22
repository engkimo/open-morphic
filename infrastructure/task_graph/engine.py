"""LangGraphTaskEngine — DAG-based task execution with parallel support."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING

from langgraph.graph import END, StateGraph

from domain.entities.task import SubTask, TaskEntity
from domain.ports.llm_gateway import LLMGateway
from domain.ports.task_engine import TaskEngine
from domain.services.agent_engine_router import AgentEngineRouter
from domain.services.answer_extractor import AnswerExtractor
from domain.services.artifact_extractor import ArtifactExtractor
from domain.services.conflict_resolver import ConflictResolver
from domain.services.execution_prompt_builder import ExecutionPromptBuilder
from domain.services.subtask_type_classifier import SubtaskTypeClassifier
from domain.services.task_complexity import TaskComplexityClassifier
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.status import SubTaskStatus
from domain.value_objects.task_complexity import TaskComplexity
from infrastructure.context_engineering.kv_cache_optimizer import KVCacheOptimizer
from infrastructure.context_engineering.observation_diversifier import (
    ObservationDiversifier,
)
from infrastructure.task_graph.code_executor import extract_and_execute
from infrastructure.task_graph.intent_analyzer import IntentAnalyzer
from infrastructure.task_graph.react_executor import ReactExecutor
from infrastructure.task_graph.state import AgentState

if TYPE_CHECKING:
    from application.use_cases.route_to_engine import RouteToEngineUseCase

TOOL_USAGE_INSTRUCTION = (
    "You have access to tools. IMPORTANT RULES:\n"
    "- For simple questions (math, factual knowledge, definitions),\n"
    "  respond with the answer directly WITHOUT calling any tools.\n"
    "- Use web_search ONLY when you need real-world information\n"
    "  you don't already know. NEVER make up data.\n"
    "- When calling web_search, extract the SPECIFIC topic/entity from the\n"
    "  task description and use it directly as the query. NEVER use generic\n"
    "  terms like '検索キーワード' or 'search keyword' as the query.\n"
    "  Example: If task says 'research Hikawa Shrine history',\n"
    "  call web_search(query='氷川神社 歴史').\n"
    "- Use web_fetch to read full page content after finding URLs.\n"
    "- If the task requires creating a FILE (slide, report, code file, etc.),\n"
    "  you MUST actually create it using fs_write. Merely describing what\n"
    "  a file would contain does NOT count as completing the task.\n"
    "- When you have gathered enough information, provide your\n"
    "  final answer directly.\n"
    "- If a tool returns an error, try an alternative approach.\n"
    "- Do NOT call a tool if you already have the answer."
)

_DISCUSSION_PROMPT = """\
You are a synthesis expert. Multiple AI models have independently worked on \
different aspects of the same task. Review their outputs, detect contradictions, \
and produce a unified final answer.

Original goal: {goal}

Model outputs:
{model_outputs}

{conflict_info}

Instructions:
- Identify agreements and contradictions between the models
- Cite which model contributed which information
- Produce a coherent, unified answer that leverages the best of each model
- If any model cited real data/URLs, preserve those citations"""

_CRITIQUE_PROMPT = """\
You are a critical reviewer in a multi-agent discussion. Another AI model \
produced a synthesis of multiple model outputs. Your task is to critically \
evaluate and improve it.

Original goal: {goal}

Original model outputs:
{model_outputs}

Previous synthesis (Round {prev_round}, by {synthesis_model}):
{previous_synthesis}

Instructions:
- Identify factual errors, unsupported claims, or logical gaps
- Add relevant information that was overlooked
- Correct contradictions between models
- Preserve citations and data sources
- Produce an improved, refined answer
- If the synthesis is already excellent, confirm and add your assessment"""

# Cloud model to auto-upgrade to when Ollama fails to generate tool calls.
# Preference: Claude Sonnet (best tool-calling), then GPT, then Gemini.
_AUTO_UPGRADE_MODELS = ("claude-sonnet-4-6", "o4-mini", "gemini/gemini-2.5-flash")

# Sprint 12.2: Model ID → AgentEngineType mapping for per-engine routing.
_MODEL_TO_ENGINE: dict[str, AgentEngineType] = {
    "claude-sonnet-4-6": AgentEngineType.CLAUDE_CODE,
    "claude-opus-4-6": AgentEngineType.CLAUDE_CODE,
    "claude-haiku-4-5-20251001": AgentEngineType.CLAUDE_CODE,
    "o4-mini": AgentEngineType.CODEX_CLI,
    "gpt-4o": AgentEngineType.CODEX_CLI,
    "gpt-4o-mini": AgentEngineType.CODEX_CLI,
}

# Prefix-based engine detection (gemini/*, ollama/*).
_MODEL_PREFIX_TO_ENGINE: list[tuple[str, AgentEngineType]] = [
    ("gemini/", AgentEngineType.GEMINI_CLI),
    ("ollama/", AgentEngineType.OLLAMA),
]


_URL_RE = re.compile(r"https?://[^\s)<>\"']+")


def _extract_urls(text: str) -> list[str]:
    """Extract unique URLs from text for data_sources tracking."""
    return list(dict.fromkeys(_URL_RE.findall(text)))


def _resolve_engine_type(model: str | None) -> AgentEngineType | None:
    """Map a model ID to an AgentEngineType. Returns None if unknown."""
    if model is None:
        return None
    if model in _MODEL_TO_ENGINE:
        return _MODEL_TO_ENGINE[model]
    for prefix, engine in _MODEL_PREFIX_TO_ENGINE:
        if model.startswith(prefix):
            return engine
    return None


def _infer_engine_from_model(model: str | None) -> str:
    """Infer a human-readable engine label from the model name.

    Used by ReAct and direct-LLM paths to populate engine_used for UI.
    """
    if not model:
        return "ollama"
    m = model.lower()
    if m.startswith("ollama/") or m in {"qwen3:8b", "qwen3-coder:30b", "deepseek-r1:8b"}:
        return "ollama"
    if "claude" in m:
        return "anthropic"
    if "gemini" in m or "google" in m:
        return "google"
    if "gpt" in m or "o4-" in m or "codex" in m:
        return "openai"
    return "litellm"


logger = logging.getLogger(__name__)


class LangGraphTaskEngine(TaskEngine):
    """Execute task subtasks through a LangGraph StateGraph DAG.

    Graph flow:
        select_ready → execute_batch → [route]
            ├── "continue" → select_ready  (more subtasks ready)
            ├── "done"     → finalize → END (all completed)
            └── "failed"   → finalize → END (blocked / exhausted retries)

    Parallel execution: independent subtasks run via asyncio.gather.
    Retry: failed subtasks retry up to MAX_RETRIES times.
    """

    MAX_RETRIES = 2

    def __init__(
        self,
        llm: LLMGateway,
        analyzer: IntentAnalyzer,
        kv_cache: KVCacheOptimizer | None = None,
        observation_diversifier: ObservationDiversifier | None = None,
        react_executor: ReactExecutor | None = None,
        route_to_engine: RouteToEngineUseCase | None = None,
        discussion_max_rounds: int = 1,
        discussion_rotate_models: bool = True,
        discussion_adaptive: bool = False,
        discussion_convergence_threshold: float = 0.85,
        discussion_min_rounds: int = 1,
        task_budget: float = 1.0,
    ) -> None:
        self._llm = llm
        self._analyzer = analyzer
        self._kv_cache = kv_cache or KVCacheOptimizer()
        self._diversifier = observation_diversifier or ObservationDiversifier()
        self._prompt_builder = ExecutionPromptBuilder(self._kv_cache.stable_prefix)
        self._react = react_executor
        self._route_to_engine = route_to_engine
        self._discussion_max_rounds = max(1, discussion_max_rounds)
        self._discussion_rotate_models = discussion_rotate_models
        self._discussion_adaptive = discussion_adaptive
        self._discussion_convergence_threshold = discussion_convergence_threshold
        self._discussion_min_rounds = max(1, discussion_min_rounds)
        self._task_budget = task_budget
        self._task: TaskEntity | None = None
        self._retry_counts: dict[str, int] = {}
        # SSE streaming: set by ExecuteTaskUseCase before execute()
        self._event_bus: object | None = None  # shared.event_bus.TaskEventBus
        self._task_repo: object | None = None  # TaskRepository for intermediate writes

    def _emit(self, event_type: str, **data: object) -> None:
        """Push an SSE event if event_bus is wired."""
        if self._event_bus is not None and self._task is not None:
            self._event_bus.publish(self._task.id, {"type": event_type, **data})  # type: ignore[union-attr]

    async def _persist_intermediate(self) -> None:
        """Write current task state to DB so WebSocket/page-refresh see updates."""
        if self._task_repo is not None and self._task is not None:
            try:
                # Keep task-level cost in sync with subtask costs
                self._task.total_cost_usd = sum(
                    s.cost_usd for s in self._task.subtasks
                )
                await self._task_repo.update(self._task)  # type: ignore[union-attr]
            except Exception:
                logger.debug("Intermediate persist failed — non-fatal", exc_info=True)

    async def decompose(self, goal: str) -> list[SubTask]:
        """Delegate to IntentAnalyzer for LLM-powered decomposition."""
        logger.info("Decomposing goal: %s", goal[:80])
        subtasks = await self._analyzer.decompose(goal)
        logger.info("Decomposed into %d subtask(s)", len(subtasks))
        return subtasks

    async def execute(self, task: TaskEntity) -> TaskEntity:
        """Run all subtasks through the LangGraph DAG."""
        logger.info("Executing task %s — %d subtask(s)", task.id[:8], len(task.subtasks))
        self._task = task
        self._retry_counts = {}

        # SSE: announce task execution start
        self._emit(
            "task_started",
            status="running",
            subtask_count=len(task.subtasks),
            subtasks=[
                {"id": s.id, "description": s.description, "dependencies": s.dependencies}
                for s in task.subtasks
            ],
        )

        graph = self._build_graph()
        initial: AgentState = {
            "ready_ids": [],
            "history": [],
            "status": "running",
            "cost_so_far": 0.0,
        }
        final_state = await graph.ainvoke(initial)

        self._task.total_cost_usd = final_state["cost_so_far"]

        return self._task

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)
        graph.add_node("select_ready", self._select_ready)
        graph.add_node("execute_batch", self._execute_batch)
        graph.add_node("finalize", self._finalize)

        graph.set_entry_point("select_ready")
        graph.add_edge("select_ready", "execute_batch")
        graph.add_conditional_edges(
            "execute_batch",
            self._route_after_execution,
            {"continue": "select_ready", "done": "finalize", "failed": "finalize"},
        )
        graph.add_edge("finalize", END)
        return graph.compile()

    # ── Graph nodes ──

    def _select_ready(self, state: AgentState) -> dict:
        """Find subtasks whose dependencies are all completed."""
        assert self._task is not None
        ready = self._task.get_ready_subtasks()
        return {"ready_ids": [s.id for s in ready]}

    def _inject_artifacts(self, subtask: SubTask) -> None:
        """Sprint 13.4a: Populate subtask input_artifacts from completed dependencies.

        For each key in subtask.input_artifacts, find the matching output_artifact
        in completed dependency subtasks. This chains artifacts along DAG edges.
        """
        assert self._task is not None
        if not subtask.input_artifacts:
            return

        # Collect all output_artifacts from completed subtasks
        available: dict[str, str] = {}
        for s in self._task.subtasks:
            if s.status in (SubTaskStatus.SUCCESS, SubTaskStatus.DEGRADED) and s.output_artifacts:
                available.update(s.output_artifacts)

        # Fill in input_artifacts with actual content
        for key in subtask.input_artifacts:
            if key in available and available[key]:
                subtask.input_artifacts[key] = available[key]

    @staticmethod
    def _build_artifact_context(artifacts: dict[str, str]) -> str:
        """Build a prompt section from input_artifacts for injection."""
        filled = {k: v for k, v in artifacts.items() if v}
        if not filled:
            return ""
        parts = ["Artifacts from previous steps:"]
        for name, content in filled.items():
            # Truncate very long artifacts to avoid context overflow
            truncated = content[:4000] + "..." if len(content) > 4000 else content
            parts.append(f"### {name}\n{truncated}")
        return "\n\n".join(parts) + "\n\n"

    @staticmethod
    def _extract_output_artifacts(subtask: SubTask) -> None:
        """Sprint 13.4b: Smart extraction of artifacts from subtask output.

        Uses ArtifactExtractor to parse the subtask's output text and match
        extracted content (code blocks, URLs, JSON data) to the artifact keys
        defined during planning.  Falls back to positional assignment from
        result/code/execution_output for keys that don't match any content type.

        For engine-routed subtasks, all content is in ``result`` — the extractor
        parses it to find code blocks, URLs, etc.  For direct LLM subtasks,
        ``code`` and ``execution_output`` may also be set and are wrapped in
        fences before extraction so they appear as code blocks.
        """
        if not subtask.output_artifacts:
            return

        keys = list(subtask.output_artifacts.keys())

        # Collect positional fallback values (Sprint 13.4a behaviour)
        fallback_values = [
            subtask.result or "",
            subtask.code or "",
            subtask.execution_output or "",
        ]
        fallback_values = [v for v in fallback_values if v]

        # Build combined text for smart extraction.
        # Wrap bare code in fences so the extractor can find it.
        parts: list[str] = []
        if subtask.result:
            parts.append(subtask.result)
        if subtask.code and "```" not in (subtask.result or ""):
            parts.append(f"```\n{subtask.code}\n```")
        if subtask.execution_output:
            parts.append(subtask.execution_output)
        combined = "\n\n".join(parts)

        matched = ArtifactExtractor.extract_and_match(
            text=combined,
            keys=keys,
            fallback_values=fallback_values,
        )
        subtask.output_artifacts.update(matched)

    async def _execute_batch(self, state: AgentState) -> dict:
        """Execute all ready subtasks in parallel via asyncio.gather."""
        assert self._task is not None
        ready_ids = state["ready_ids"]
        cost = state["cost_so_far"]
        history: list[dict] = []
        subtask_map = {s.id: s for s in self._task.subtasks}

        async def execute_one(subtask_id: str) -> dict:
            subtask = subtask_map[subtask_id]
            subtask.status = SubTaskStatus.RUNNING

            # SSE: notify subscribers that this subtask started
            self._emit(
                "subtask_started",
                subtask_id=subtask_id,
                description=subtask.description,
                dependencies=subtask.dependencies,
            )
            await self._persist_intermediate()

            # Sprint 13.4a: Inject artifacts from completed dependencies
            self._inject_artifacts(subtask)
            artifact_context = self._build_artifact_context(subtask.input_artifacts)

            logger.info("Running subtask %s: %s", subtask_id, subtask.description[:60])
            complexity = subtask.complexity or TaskComplexity.MEDIUM
            config = self._prompt_builder.build(
                description=subtask.description,
                complexity=complexity,
                goal=self._task.goal,
            )
            try:
                # Sprint 13.3: Inject role context into execution prompt.
                # Roles are free-form strings from user or LLM — no hardcoded types.
                role_prefix = ""
                if subtask.role:
                    role_prefix = (
                        f"You are acting as: {subtask.role}. "
                        f"Approach the task from this perspective.\n\n"
                    )

                # Sprint 12.2 + TD-155: Per-engine autonomous execution.
                # Two paths to determine engine:
                #   A) Explicit: preferred_model → _resolve_engine_type
                #   B) Auto-route: classify subtask → AgentEngineRouter.select
                # Both route through RouteToEngineUseCase with fallback chain.
                engine_type = _resolve_engine_type(subtask.preferred_model)

                # TD-155: Auto-route — classify subtask when no model specified
                if engine_type is None and self._route_to_engine is not None:
                    inferred_type = SubtaskTypeClassifier.infer(
                        subtask.description,
                    )
                    auto_engine = AgentEngineRouter.select(
                        task_type=inferred_type,
                        budget=self._task_budget,
                    )
                    # Only use engine routing for non-OLLAMA engines
                    # (OLLAMA is handled more efficiently by ReactExecutor/direct LLM)
                    if auto_engine != AgentEngineType.OLLAMA:
                        engine_type = auto_engine
                        logger.info(
                            "Auto-route subtask %s: type=%s → engine=%s",
                            subtask_id,
                            inferred_type.value,
                            auto_engine.value,
                        )

                use_engine_route = (
                    self._route_to_engine is not None and engine_type is not None
                )

                executed_via_engine = False
                if use_engine_route:
                    assert self._route_to_engine is not None
                    engine_task = artifact_context + role_prefix + config.user_prompt
                    engine_result = await self._route_to_engine.execute(
                        task=engine_task,
                        preferred_engine=engine_type,
                        model=subtask.preferred_model,
                        task_id=self._task.id,
                    )
                    if engine_result.success:
                        # TD-156: If auto-route intended a capable engine but
                        # fell back to OLLAMA for a tool-requiring task, reject
                        # the OLLAMA answer and let ReactExecutor + auto-upgrade
                        # handle it with a cloud model that supports tool-calling.
                        task_needs_tools = TaskComplexityClassifier.requires_tools(
                            subtask.description,
                        )
                        fell_to_ollama = (
                            engine_result.engine == AgentEngineType.OLLAMA
                        )
                        intended_capable = (
                            engine_type is not None
                            and engine_type != AgentEngineType.OLLAMA
                        )
                        if task_needs_tools and fell_to_ollama and intended_capable:
                            logger.warning(
                                "Subtask %s requires tools but all capable engines "
                                "unavailable (intended=%s, tried=%s) — "
                                "falling through to ReactExecutor with auto-upgrade",
                                subtask_id,
                                engine_type.value,
                                engine_result.engines_tried,
                            )
                        else:
                            subtask.status = SubTaskStatus.SUCCESS
                            subtask.result = AnswerExtractor.extract(
                                engine_result.output, complexity,
                            )
                            subtask.model_used = (
                                engine_result.model_used or subtask.preferred_model
                            )
                            subtask.cost_usd = engine_result.cost_usd
                            subtask.engine_used = engine_result.engine.value
                            executed_via_engine = True
                            # Extract URLs from engine output for observability
                            urls = _extract_urls(engine_result.output)
                            if urls:
                                subtask.data_sources = urls
                            logger.info(
                                "Subtask %s (engine=%s) — model=%s cost=$%.6f data_sources=%d",
                                subtask_id,
                                subtask.engine_used,
                                subtask.model_used,
                                subtask.cost_usd,
                                len(urls),
                            )
                    else:
                        logger.warning(
                            "Engine route failed for subtask %s (%s): %s — falling back to ReAct",
                            subtask_id,
                            engine_type.value if engine_type else "?",
                            engine_result.error,
                        )

                # Complexity-aware execution path selection:
                # Simple tasks that don't require tools → direct LLM call
                # (avoids Ollama getting distracted by 38+ tool schemas).
                # Tool-requiring tasks and MEDIUM/COMPLEX → ReAct loop.
                use_react = self._react is not None and (
                    complexity != TaskComplexity.SIMPLE
                    or TaskComplexityClassifier.requires_tools(subtask.description)
                )

                if not executed_via_engine and use_react:
                    # ReAct path: iterative tool-augmented execution
                    react_system = (
                        artifact_context
                        + role_prefix
                        + config.system_prompt
                        + "\n\n"
                        + TOOL_USAGE_INSTRUCTION
                    )
                    result = await self._react.execute(
                        system_prompt=react_system,
                        user_prompt=config.user_prompt,
                        model=subtask.preferred_model,
                        temperature=config.temperature,
                        max_tokens=config.max_tokens,
                    )

                    # Sprint 12.6: Auto-upgrade — if task requires tools but
                    # no tool calls were generated (Ollama can't function-call),
                    # retry with a cloud model that supports tool-calling.
                    task_needs_tools = TaskComplexityClassifier.requires_tools(subtask.description)
                    if (
                        task_needs_tools
                        and result.trace.total_iterations > 0
                        and sum(len(s.tool_calls) for s in result.trace.steps) == 0
                        and not subtask.preferred_model  # don't override explicit choice
                    ):
                        upgrade_model = await self._pick_upgrade_model()
                        if upgrade_model:
                            logger.info(
                                "Auto-upgrade: subtask %s requires tools but model "
                                "%s produced none — retrying with %s",
                                subtask_id,
                                result.model_used,
                                upgrade_model,
                            )
                            result = await self._react.execute(
                                system_prompt=react_system,
                                user_prompt=config.user_prompt,
                                model=upgrade_model,
                                temperature=config.temperature,
                                max_tokens=config.max_tokens,
                            )

                    # TD-180: Detect incomplete execution (max_iterations or repetitive loops)
                    _term = result.trace.terminated_reason
                    if _term in ("max_iterations", "repetitive_tool_loop"):
                        subtask.status = SubTaskStatus.FAILED
                        subtask.error = f"ReAct terminated: {_term}"
                        logger.warning(
                            "Subtask %s marked FAILED — terminated_reason=%s",
                            subtask_id, _term,
                        )
                    else:
                        subtask.status = SubTaskStatus.SUCCESS
                    subtask.result = AnswerExtractor.extract(result.final_answer, complexity)
                    subtask.model_used = result.model_used
                    subtask.cost_usd = result.total_cost_usd
                    subtask.tool_calls_count = sum(len(s.tool_calls) for s in result.trace.steps)
                    subtask.react_iterations = result.trace.total_iterations
                    # TD-158: Always set engine_used for UI visibility
                    subtask.engine_used = _infer_engine_from_model(result.model_used)
                    # Sprint 12.1: stamp tools_used and data_sources
                    if result.tools_used:
                        subtask.tools_used = result.tools_used
                    if result.data_sources:
                        subtask.data_sources = result.data_sources
                    logger.info(
                        "Subtask %s (ReAct) — engine=%s model=%s cost=$%.6f "
                        "iterations=%d tools=%d tools_used=%s",
                        subtask_id,
                        subtask.engine_used,
                        result.model_used,
                        result.total_cost_usd,
                        subtask.react_iterations,
                        subtask.tool_calls_count,
                        subtask.tools_used or "none",
                    )
                elif not executed_via_engine:
                    # Legacy path: single LLM completion
                    sys_content = artifact_context + role_prefix + config.system_prompt
                    messages = [
                        {"role": "system", "content": sys_content},
                        {"role": "user", "content": config.user_prompt},
                    ]
                    response = await self._llm.complete(
                        messages,
                        temperature=config.temperature,
                        max_tokens=config.max_tokens,
                        model=subtask.preferred_model,
                    )
                    subtask.status = SubTaskStatus.SUCCESS
                    subtask.result = AnswerExtractor.extract(response.content, complexity)
                    subtask.model_used = response.model
                    subtask.cost_usd = response.cost_usd
                    # TD-158: Always set engine_used for UI visibility
                    subtask.engine_used = _infer_engine_from_model(response.model)

                    # Sprint 9.2: Extract and execute code blocks from LLM output
                    exec_result = await extract_and_execute(response.content)
                    if exec_result is not None:
                        subtask.code = exec_result.code
                        subtask.execution_output = (
                            exec_result.output if exec_result.success else exec_result.error
                        )
                        logger.info(
                            "Code execution — lang=%s success=%s output_len=%d",
                            exec_result.language,
                            exec_result.success,
                            len(exec_result.output) if exec_result.output else 0,
                        )

                    logger.info(
                        "Subtask %s completed — model=%s cost=$%.6f",
                        subtask_id,
                        response.model,
                        response.cost_usd,
                    )

                # Sprint 13.4a: Extract output artifacts from completed subtask
                self._extract_output_artifacts(subtask)

                # SSE: notify subscribers that this subtask completed
                self._emit(
                    "subtask_completed",
                    subtask_id=subtask_id,
                    status=subtask.status.value,
                    result=subtask.result[:500] if subtask.result else None,
                    model_used=subtask.model_used,
                    engine_used=subtask.engine_used,
                    cost_usd=subtask.cost_usd,
                )
                await self._persist_intermediate()

                return {
                    "subtask_id": subtask_id,
                    "status": "success",
                    "model": subtask.model_used,
                    "cost": subtask.cost_usd,
                }
            except Exception as e:
                count = self._retry_counts.get(subtask_id, 0) + 1
                self._retry_counts[subtask_id] = count
                if count < self.MAX_RETRIES:
                    logger.warning(
                        "Subtask %s failed (retry %d/%d): %s",
                        subtask_id,
                        count,
                        self.MAX_RETRIES,
                        e,
                    )
                    subtask.status = SubTaskStatus.PENDING
                    subtask.error = None
                else:
                    logger.error("Subtask %s failed permanently: %s", subtask_id, e)
                    subtask.status = SubTaskStatus.FAILED
                    subtask.error = str(e)
                # SSE: notify subscribers of failure
                self._emit(
                    "subtask_completed",
                    subtask_id=subtask_id,
                    status=subtask.status.value,
                    error=str(e),
                    cost_usd=0.0,
                )
                await self._persist_intermediate()
                return {
                    "subtask_id": subtask_id,
                    "status": "failed",
                    "error": str(e),
                    "retry": count,
                    "cost": 0.0,
                }

        results = await asyncio.gather(*[execute_one(sid) for sid in ready_ids])

        for idx, r in enumerate(results):
            cost += r.get("cost", 0.0)
            r["formatted"] = self._diversifier.serialize(r, len(state["history"]) + idx)
            history.append(r)

        return {"cost_so_far": cost, "history": history}

    def _route_after_execution(self, state: AgentState) -> str:
        """Decide next step: continue, done, or failed."""
        assert self._task is not None
        ready = self._task.get_ready_subtasks()

        if ready:
            return "continue"
        if self._task.is_complete:
            return "done"

        # Pending subtasks exist but none are ready → blocked by failed deps
        pending = [s for s in self._task.subtasks if s.status == SubTaskStatus.PENDING]
        if pending:
            for s in pending:
                s.status = SubTaskStatus.FAILED
                s.error = "Blocked: dependency failed"
            return "failed"

        return "done"

    async def _pick_upgrade_model(self) -> str | None:
        """Pick the first available auto-upgrade model for tool-calling.

        Checks LLMGateway.is_available() for each candidate, returning
        the first model with a valid API key. Returns None if none available.
        """
        for model in _AUTO_UPGRADE_MODELS:
            if await self._llm.is_available(model):
                return model
        return None

    def _is_multi_model(self) -> bool:
        """Check if the task used multiple distinct models."""
        assert self._task is not None
        models = {
            s.model_used
            for s in self._task.subtasks
            if s.model_used and s.status in (SubTaskStatus.SUCCESS, SubTaskStatus.DEGRADED)
        }
        return len(models) >= 2

    async def _pick_discussion_model(self, exclude_models: set[str]) -> str | None:
        """Pick a model for discussion critique, excluding already-used models.

        Ensures each discussion round uses a different model for diverse perspectives.
        Returns None if no alternative model is available (will use default).
        """
        for model in _AUTO_UPGRADE_MODELS:
            if model not in exclude_models and await self._llm.is_available(model):
                return model
        return None

    async def _run_discussion(self, state: AgentState) -> float:
        """Sprint 12.3 + 13.1 + 13.5: Iterative multi-round discussion.

        Round 1: Collect all results → ConflictResolver → synthesis.
        Round 2+: Different model critiques previous synthesis → refined answer.

        Configurable via discussion_max_rounds and discussion_rotate_models.
        When max_rounds=1, behaves identically to the original single-shot synthesis.

        Sprint 13.5: When discussion_adaptive=True, detect convergence between
        consecutive rounds and stop early if the discussion has stabilized.
        """
        assert self._task is not None
        from domain.ports.insight_extractor import ExtractedInsight
        from domain.value_objects.cognitive import CognitiveMemoryType

        completed = [
            s
            for s in self._task.subtasks
            if s.status in (SubTaskStatus.SUCCESS, SubTaskStatus.DEGRADED) and s.result
        ]
        if len(completed) < 2:
            return 0.0

        # Build ExtractedInsight objects for ConflictResolver
        insights: list[ExtractedInsight] = []
        model_outputs_parts: list[str] = []
        for s in completed:
            engine = AgentEngineType.OLLAMA
            if s.engine_used:
                import contextlib

                with contextlib.suppress(ValueError):
                    engine = AgentEngineType(s.engine_used)
            elif s.model_used:
                resolved = _resolve_engine_type(s.model_used)
                engine = resolved or AgentEngineType.OLLAMA

            insights.append(
                ExtractedInsight(
                    content=s.result or "",
                    memory_type=CognitiveMemoryType.EPISODIC,
                    confidence=0.7,
                    source_engine=engine,
                )
            )
            role_tag = f", role: {s.role}" if s.role else ""
            model_outputs_parts.append(
                f"### {s.model_used or 'unknown'} "
                f"(subtask: {s.description[:60]}{role_tag})\n{s.result}"
            )

        # Run ConflictResolver
        survivors, conflicts = ConflictResolver.resolve_all(insights)
        conflict_info = ""
        if conflicts:
            conflict_lines = []
            for cp in conflicts:
                winner_engine = cp.resolved_winner.source_engine.value
                conflict_lines.append(
                    f"- Conflict (overlap={cp.overlap_score:.2f}): winner={winner_engine}"
                )
            conflict_info = "Detected conflicts:\n" + "\n".join(conflict_lines)

        # ── Multi-round discussion loop ──
        # Sprint 13.2: Each round tries engine routing first (autonomous agent
        # runtime that can write code, execute, search, iterate) then falls back
        # to direct LLM API.  This is a generic framework capability — engines
        # bring autonomous reasoning, not just text generation.
        model_outputs_text = "\n\n".join(model_outputs_parts)
        total_cost = 0.0
        previous_synthesis: str | None = None
        synthesis_model: str | None = None
        last_engine_used: str | None = None
        models_used: set[str] = set()
        final_round = 0
        # Sprint 13.4a: Accumulate discussion artifacts across rounds
        discussion_artifacts: dict[str, str] = {}
        # Sprint 13.5: Track previous round text for convergence detection
        prev_round_text: str | None = None

        for round_num in range(1, self._discussion_max_rounds + 1):
            final_round = round_num

            # Sprint 13.4a: Build artifact context for discussion rounds
            artifact_section = self._build_artifact_context(discussion_artifacts)

            if round_num == 1:
                # Round 1: Initial synthesis (original behavior)
                prompt = _DISCUSSION_PROMPT.format(
                    goal=self._task.goal,
                    model_outputs=model_outputs_text,
                    conflict_info=conflict_info,
                )
                user_msg = (
                    artifact_section + "Synthesize the above model outputs into a unified answer."
                )
            else:
                # Round 2+: Critique & refine previous synthesis
                prompt = _CRITIQUE_PROMPT.format(
                    goal=self._task.goal,
                    model_outputs=model_outputs_text,
                    prev_round=round_num - 1,
                    synthesis_model=synthesis_model or "unknown",
                    previous_synthesis=previous_synthesis or "",
                )
                user_msg = (
                    artifact_section + "Critically evaluate and improve the previous synthesis."
                )

            # Select model for this round (rotate for diversity)
            discussion_model: str | None = None
            if round_num > 1 and self._discussion_rotate_models:
                discussion_model = await self._pick_discussion_model(models_used)

            # ── Sprint 13.2: Try engine-routed discussion ──
            # Engine runtimes (Claude Code CLI, Gemini CLI, etc.) can write code,
            # execute it, search the web, and iterate — producing richer analysis
            # than a single LLM completion.
            engine_type = _resolve_engine_type(discussion_model) if discussion_model else None
            engine_succeeded = False

            if self._route_to_engine is not None and engine_type is not None:
                engine_task = f"{prompt}\n\n{user_msg}"
                try:
                    engine_result = await self._route_to_engine.execute(
                        task=engine_task,
                        preferred_engine=engine_type,
                        model=discussion_model,
                        task_id=self._task.id if self._task else None,
                    )
                    if engine_result.success:
                        previous_synthesis = engine_result.output
                        synthesis_model = engine_result.model_used or discussion_model
                        models_used.add(synthesis_model)
                        total_cost += engine_result.cost_usd
                        last_engine_used = engine_result.engine.value
                        engine_succeeded = True
                        discussion_artifacts[f"round_{round_num}"] = previous_synthesis
                        logger.info(
                            "Discussion round %d/%d — engine=%s model=%s cost=$%.6f",
                            round_num,
                            self._discussion_max_rounds,
                            engine_result.engine.value,
                            synthesis_model,
                            engine_result.cost_usd,
                        )
                except Exception:
                    logger.warning(
                        "Engine-routed discussion round %d failed — falling back to LLM",
                        round_num,
                        exc_info=True,
                    )

            # ── Fallback: direct LLM API ──
            if not engine_succeeded:
                messages = [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_msg},
                ]
                try:
                    response = await self._llm.complete(
                        messages, temperature=0.3, max_tokens=2048, model=discussion_model
                    )
                    previous_synthesis = response.content
                    synthesis_model = response.model
                    models_used.add(response.model)
                    total_cost += response.cost_usd
                    last_engine_used = None
                    discussion_artifacts[f"round_{round_num}"] = previous_synthesis
                    logger.info(
                        "Discussion round %d/%d — model=%s cost=$%.6f",
                        round_num,
                        self._discussion_max_rounds,
                        response.model,
                        response.cost_usd,
                    )
                except Exception:
                    logger.warning(
                        "Discussion round %d failed — stopping", round_num, exc_info=True
                    )
                    break

            # Sprint 13.5: Adaptive convergence check — stop early if stabilized
            if self._discussion_adaptive and previous_synthesis is not None:
                from domain.services.convergence_detector import ConvergenceDetector

                should_go, conv_result = ConvergenceDetector.should_continue(
                    rounds_completed=round_num,
                    min_rounds=self._discussion_min_rounds,
                    max_rounds=self._discussion_max_rounds,
                    previous_text=prev_round_text,
                    current_text=previous_synthesis,
                    threshold=self._discussion_convergence_threshold,
                )
                if conv_result is not None:
                    logger.info(
                        "Convergence check R%d: converged=%s similarity=%.3f signals=%s",
                        round_num,
                        conv_result.converged,
                        conv_result.similarity,
                        conv_result.signals,
                    )
                if not should_go:
                    logger.info(
                        "Discussion converged at round %d/%d — stopping early",
                        round_num,
                        self._discussion_max_rounds,
                    )
                    break
            prev_round_text = previous_synthesis

        if previous_synthesis is None:
            return 0.0

        # Create synthesis subtask with final round's result
        round_label = f" R{final_round}" if self._discussion_max_rounds > 1 else ""
        engine_label = f" via {last_engine_used}" if last_engine_used else ""
        description = (
            f"[Discussion{round_label}{engine_label}] "
            f"Cross-validate and unify {len(completed)} model outputs"
        )

        synthesis_subtask = SubTask(
            description=description,
            status=SubTaskStatus.SUCCESS,
            result=previous_synthesis,
            model_used=synthesis_model,
            cost_usd=total_cost,
            engine_used=last_engine_used,
        )
        self._task.subtasks.append(synthesis_subtask)
        logger.info(
            "Discussion phase — %d round(s), %d model(s) (%s), engine=%s, %d conflicts, cost=$%.6f",
            final_round,
            len(models_used),
            ", ".join(sorted(models_used)),
            last_engine_used or "none",
            len(conflicts),
            total_cost,
        )
        return total_cost

    async def _finalize(self, state: AgentState) -> dict:
        """Set final execution status.

        Sprint 12.3: Run discussion phase for multi-model tasks.
        Sprint 12.5: Validate tool-requiring subtasks. If a subtask required
        tools (web search etc.) but none were used, downgrade from SUCCESS
        to DEGRADED — "completed without tools".
        """
        assert self._task is not None

        # Sprint 12.3: Discussion phase for multi-model tasks
        discussion_cost = 0.0
        if self._is_multi_model():
            discussion_cost = await self._run_discussion(state)

        # Sprint 12.5: DEGRADED validation
        # Skip agent-CLI-routed subtasks — autonomous runtimes handle tools internally.
        # TD-158: Only skip for real CLI engines, not LLM-inferred labels.
        autonomous_engines = {"claude_code", "gemini_cli", "codex_cli", "openhands", "adk"}
        for st in self._task.subtasks:
            if st.status != SubTaskStatus.SUCCESS:
                continue
            if st.engine_used in autonomous_engines:
                continue  # trust autonomous engine's tool usage
            if not TaskComplexityClassifier.requires_tools(st.description):
                continue
            if not st.tools_used:
                logger.warning(
                    "Subtask %s requires tools but none were used — marking DEGRADED",
                    st.id,
                )
                st.status = SubTaskStatus.DEGRADED

        total_cost = state["cost_so_far"] + discussion_cost
        rate = self._task.success_rate
        has_degraded = any(s.status == SubTaskStatus.DEGRADED for s in self._task.subtasks)
        if rate == 1.0 and not has_degraded:
            status = "done"
        elif rate > 0:
            status = "done"  # partial success (some DEGRADED)
        else:
            status = "failed"

        logger.info(
            "Task %s finalized — status=%s success_rate=%.0f%% degraded=%d total_cost=$%.6f",
            self._task.id[:8],
            status,
            rate * 100,
            sum(1 for s in self._task.subtasks if s.status == SubTaskStatus.DEGRADED),
            total_cost,
        )
        return {"status": status, "cost_so_far": total_cost}
