"""LangGraphTaskEngine — DAG-based task execution with parallel support."""

from __future__ import annotations

import asyncio

from langgraph.graph import END, StateGraph

from domain.entities.task import SubTask, TaskEntity
from domain.ports.llm_gateway import LLMGateway
from domain.ports.task_engine import TaskEngine
from domain.value_objects.status import SubTaskStatus
from infrastructure.task_graph.intent_analyzer import IntentAnalyzer
from infrastructure.task_graph.state import AgentState


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

    def __init__(self, llm: LLMGateway, analyzer: IntentAnalyzer) -> None:
        self._llm = llm
        self._analyzer = analyzer
        self._task: TaskEntity | None = None
        self._retry_counts: dict[str, int] = {}

    async def decompose(self, goal: str) -> list[SubTask]:
        """Delegate to IntentAnalyzer for LLM-powered decomposition."""
        return await self._analyzer.decompose(goal)

    async def execute(self, task: TaskEntity) -> TaskEntity:
        """Run all subtasks through the LangGraph DAG."""
        self._task = task
        self._retry_counts = {}

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
            messages = [
                {"role": "system", "content": f"Goal: {self._task.goal}"},
                {"role": "user", "content": subtask.description},
            ]
            try:
                response = await self._llm.complete(messages)
                subtask.status = SubTaskStatus.SUCCESS
                subtask.result = response.content
                subtask.model_used = response.model
                subtask.cost_usd = response.cost_usd
                return {
                    "subtask_id": subtask_id,
                    "status": "success",
                    "model": response.model,
                    "cost": response.cost_usd,
                }
            except Exception as e:
                count = self._retry_counts.get(subtask_id, 0) + 1
                self._retry_counts[subtask_id] = count
                if count < self.MAX_RETRIES:
                    subtask.status = SubTaskStatus.PENDING
                    subtask.error = None
                else:
                    subtask.status = SubTaskStatus.FAILED
                    subtask.error = str(e)
                return {
                    "subtask_id": subtask_id,
                    "status": "failed",
                    "error": str(e),
                    "retry": count,
                    "cost": 0.0,
                }

        results = await asyncio.gather(*[execute_one(sid) for sid in ready_ids])

        for r in results:
            cost += r.get("cost", 0.0)
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
        pending = [
            s for s in self._task.subtasks if s.status == SubTaskStatus.PENDING
        ]
        if pending:
            for s in pending:
                s.status = SubTaskStatus.FAILED
                s.error = "Blocked: dependency failed"
            return "failed"

        return "done"

    def _finalize(self, state: AgentState) -> dict:
        """Set final execution status."""
        assert self._task is not None
        if self._task.success_rate == 1.0:
            return {"status": "done"}
        return {"status": "failed"}
