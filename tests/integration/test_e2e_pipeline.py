"""E2E Pipeline Tests — Goal → Decompose → DAG Execute → Result.

Run with: uv run pytest tests/integration/test_e2e_pipeline.py -v -s
Requires: Ollama running with qwen3 model; optionally API keys for cloud tests.

Tests the full use case pipeline:
  CreateTaskUseCase (goal → subtasks → persist)
  → ExecuteTaskUseCase (load → DAG → parallel execute → persist)
"""

from __future__ import annotations

import asyncio
import os

import pytest

from application.use_cases.create_task import CreateTaskUseCase
from application.use_cases.execute_task import ExecuteTaskUseCase
from domain.entities.task import TaskEntity
from domain.ports.task_repository import TaskRepository
from domain.value_objects.status import SubTaskStatus, TaskStatus
from infrastructure.llm.cost_tracker import CostTracker
from infrastructure.llm.litellm_gateway import LiteLLMGateway
from infrastructure.llm.ollama_manager import OllamaManager
from infrastructure.task_graph.engine import LangGraphTaskEngine
from infrastructure.task_graph.intent_analyzer import IntentAnalyzer
from shared.config import Settings


# ── In-memory TaskRepository ──


class _InMemoryTaskRepo(TaskRepository):
    """Minimal in-memory TaskRepository for E2E tests."""

    def __init__(self) -> None:
        self._store: dict[str, TaskEntity] = {}

    async def save(self, task: TaskEntity) -> None:
        self._store[task.id] = task

    async def get_by_id(self, task_id: str) -> TaskEntity | None:
        return self._store.get(task_id)

    async def list_by_status(self, status: TaskStatus) -> list[TaskEntity]:
        return [t for t in self._store.values() if t.status == status]

    async def update(self, task: TaskEntity) -> None:
        self._store[task.id] = task

    async def delete(self, task_id: str) -> None:
        self._store.pop(task_id, None)


class _InMemoryCostRepo:
    """Minimal in-memory CostRepository for E2E tests."""

    def __init__(self) -> None:
        self._records: list = []

    async def save(self, record) -> None:
        self._records.append(record)

    async def get_daily_total(self) -> float:
        return sum(r.cost_usd for r in self._records)

    async def get_monthly_total(self) -> float:
        return sum(r.cost_usd for r in self._records)

    async def get_local_usage_rate(self) -> float:
        if not self._records:
            return 0.0
        local = sum(1 for r in self._records if r.is_local)
        return local / len(self._records)


# ── Fixtures ──


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def ollama() -> OllamaManager:
    mgr = OllamaManager()
    if not await mgr.is_running():
        pytest.skip("Ollama not running")
    return mgr


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def cost_repo() -> _InMemoryCostRepo:
    return _InMemoryCostRepo()


@pytest.fixture(scope="module")
def gateway(
    ollama: OllamaManager, cost_repo: _InMemoryCostRepo, settings: Settings
) -> LiteLLMGateway:
    if settings.has_gemini and not os.environ.get("GEMINI_API_KEY"):
        os.environ["GEMINI_API_KEY"] = settings.google_gemini_api_key
    cost_tracker = CostTracker(cost_repo)
    return LiteLLMGateway(ollama=ollama, cost_tracker=cost_tracker, settings=settings)


@pytest.fixture
def task_repo() -> _InMemoryTaskRepo:
    """Fresh repo per test to avoid cross-test interference."""
    return _InMemoryTaskRepo()


@pytest.fixture
def engine(gateway: LiteLLMGateway) -> LangGraphTaskEngine:
    analyzer = IntentAnalyzer(llm=gateway)
    return LangGraphTaskEngine(llm=gateway, analyzer=analyzer)


# ══════════════════════════════════════════════════════════
# E2E Pipeline: Local Ollama
# ══════════════════════════════════════════════════════════


class TestE2EPipelineLocal:
    """Full pipeline using local Ollama ($0 cost)."""

    async def test_create_and_execute_simple_goal(
        self, engine: LangGraphTaskEngine, task_repo: _InMemoryTaskRepo
    ) -> None:
        """Goal → decompose → persist → execute → result."""
        # Step 1: Create task (decompose goal into subtasks)
        create_uc = CreateTaskUseCase(engine=engine, repo=task_repo)
        task = await create_uc.execute("Write a Python function that checks if a number is prime")

        print(f"\n  Goal: {task.goal}")
        print(f"  Task ID: {task.id}")
        print(f"  Status: {task.status.value}")
        print(f"  Subtasks ({len(task.subtasks)}):")
        for st in task.subtasks:
            print(f"    [{st.status.value}] {st.description} (deps: {st.dependencies})")

        # Verify creation
        assert task.status == TaskStatus.PENDING
        assert len(task.subtasks) >= 2
        assert all(st.status == SubTaskStatus.PENDING for st in task.subtasks)

        # Verify persistence
        stored = await task_repo.get_by_id(task.id)
        assert stored is not None
        assert stored.id == task.id

        # Step 2: Execute task (run DAG)
        execute_uc = ExecuteTaskUseCase(engine=engine, repo=task_repo)
        result = await execute_uc.execute(task.id)

        print(f"\n  After execution:")
        print(f"  Status: {result.status.value}")
        print(f"  Success rate: {result.success_rate:.0%}")
        print(f"  Total cost: ${result.total_cost_usd:.6f}")
        for st in result.subtasks:
            model = st.model_used or "N/A"
            status_icon = "+" if st.status == SubTaskStatus.SUCCESS else "x"
            print(f"    [{status_icon}] {st.description}")
            print(f"        model={model}, cost=${st.cost_usd:.6f}")
            if st.result:
                print(f"        result={st.result[:80]}...")

        # Verify execution
        assert result.status in (TaskStatus.SUCCESS, TaskStatus.FALLBACK)
        assert result.success_rate > 0
        assert any(st.status == SubTaskStatus.SUCCESS for st in result.subtasks)
        assert any(st.result for st in result.subtasks)
        assert any(st.model_used for st in result.subtasks)

        # Verify persistence updated
        final = await task_repo.get_by_id(task.id)
        assert final.status in (TaskStatus.SUCCESS, TaskStatus.FALLBACK)

    async def test_parallel_subtask_execution(
        self, engine: LangGraphTaskEngine, task_repo: _InMemoryTaskRepo
    ) -> None:
        """Goal with independent subtasks should execute in parallel."""
        create_uc = CreateTaskUseCase(engine=engine, repo=task_repo)
        task = await create_uc.execute(
            "Create two independent Python utilities: a fibonacci function and a factorial function"
        )

        print(f"\n  Subtasks ({len(task.subtasks)}):")
        for st in task.subtasks:
            print(f"    - {st.description} (deps: {st.dependencies})")

        assert len(task.subtasks) >= 2

        # Count how many subtasks have no dependencies (can run in parallel)
        independent = [st for st in task.subtasks if not st.dependencies]
        print(f"  Independent subtasks (parallel-eligible): {len(independent)}")

        # Execute
        execute_uc = ExecuteTaskUseCase(engine=engine, repo=task_repo)
        result = await execute_uc.execute(task.id)

        print(f"  Status: {result.status.value}, success rate: {result.success_rate:.0%}")
        assert result.success_rate > 0

    async def test_subtask_results_contain_code(
        self, engine: LangGraphTaskEngine, task_repo: _InMemoryTaskRepo
    ) -> None:
        """Subtask results should contain actual code or useful output."""
        create_uc = CreateTaskUseCase(engine=engine, repo=task_repo)
        task = await create_uc.execute("Write a Python hello world function")

        execute_uc = ExecuteTaskUseCase(engine=engine, repo=task_repo)
        result = await execute_uc.execute(task.id)

        # At least one subtask should have meaningful content
        successful = [st for st in result.subtasks if st.status == SubTaskStatus.SUCCESS]
        assert len(successful) >= 1

        has_content = any(len(st.result or "") > 10 for st in successful)
        assert has_content, "At least one subtask should produce meaningful output"

        for st in successful:
            print(f"\n  [{st.description}]")
            print(f"  {(st.result or '')[:200]}")

    async def test_cost_tracking_in_pipeline(
        self, engine: LangGraphTaskEngine, task_repo: _InMemoryTaskRepo
    ) -> None:
        """Pipeline should track cumulative cost across subtasks."""
        create_uc = CreateTaskUseCase(engine=engine, repo=task_repo)
        task = await create_uc.execute("Explain what a binary search algorithm does")

        execute_uc = ExecuteTaskUseCase(engine=engine, repo=task_repo)
        result = await execute_uc.execute(task.id)

        # Local Ollama: cost should be $0
        print(f"\n  Total cost: ${result.total_cost_usd:.6f}")
        for st in result.subtasks:
            print(f"    {st.description}: ${st.cost_usd:.6f} ({st.model_used})")

        # All subtask costs should be non-negative
        assert all(st.cost_usd >= 0 for st in result.subtasks)
        # total_cost should equal sum of subtask costs
        expected_cost = sum(st.cost_usd for st in result.subtasks)
        assert abs(result.total_cost_usd - expected_cost) < 0.001


# ══════════════════════════════════════════════════════════
# E2E Pipeline: Cloud API (Anthropic)
# ══════════════════════════════════════════════════════════


class TestE2EPipelineCloud:
    """Full pipeline using cloud API (verifies non-zero cost tracking)."""

    async def test_cloud_pipeline_with_anthropic(
        self,
        ollama: OllamaManager,
        settings: Settings,
        task_repo: _InMemoryTaskRepo,
    ) -> None:
        """Full pipeline with Claude Haiku — verifies cloud cost tracking."""
        if not settings.has_anthropic:
            pytest.skip("ANTHROPIC_API_KEY not set")

        # Build a gateway that forces cloud model (not local_first)
        cloud_settings = Settings(
            local_first=False,
            anthropic_api_key=settings.anthropic_api_key,
            openai_api_key="",
            google_gemini_api_key="",
        )
        cost_repo = _InMemoryCostRepo()
        cost_tracker = CostTracker(cost_repo)
        cloud_gw = LiteLLMGateway(
            ollama=ollama, cost_tracker=cost_tracker, settings=cloud_settings
        )

        # Use Haiku to minimize cost
        class _HaikuGateway(LiteLLMGateway):
            """Force Haiku model for all completions."""
            async def complete(self, messages, model=None, **kwargs):
                return await super().complete(
                    messages, model="claude-haiku-4-5-20251001", **kwargs
                )

        haiku_gw = _HaikuGateway(
            ollama=ollama, cost_tracker=cost_tracker, settings=cloud_settings
        )

        analyzer = IntentAnalyzer(llm=haiku_gw)
        engine = LangGraphTaskEngine(llm=haiku_gw, analyzer=analyzer)

        # Create + execute
        create_uc = CreateTaskUseCase(engine=engine, repo=task_repo)
        task = await create_uc.execute("Explain what a linked list is in one sentence")

        print(f"\n  Cloud pipeline (Haiku):")
        print(f"  Subtasks: {len(task.subtasks)}")

        execute_uc = ExecuteTaskUseCase(engine=engine, repo=task_repo)
        result = await execute_uc.execute(task.id)

        print(f"  Status: {result.status.value}")
        print(f"  Total cost: ${result.total_cost_usd:.6f}")
        for st in result.subtasks:
            print(f"    [{st.status.value}] {st.description}")
            print(f"        model={st.model_used}, cost=${st.cost_usd:.6f}")

        # Cloud model should have non-zero cost
        assert result.status in (TaskStatus.SUCCESS, TaskStatus.FALLBACK)
        assert result.total_cost_usd > 0, "Cloud pipeline should have non-zero cost"
        assert all("claude" in (st.model_used or "") for st in result.subtasks
                    if st.status == SubTaskStatus.SUCCESS)
        assert len(cost_repo._records) >= 1
