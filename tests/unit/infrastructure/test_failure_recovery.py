"""E2E Failure Recovery Tests — fail → retry → success/fallback.

Tests the LangGraphTaskEngine retry mechanism:
- Subtask failure triggers automatic retry (up to MAX_RETRIES=2)
- After retries exhausted, subtask is marked FAILED
- Dependent subtasks are blocked and marked FAILED
- Partial success → FALLBACK status
- Total failure → FAILED status
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from application.use_cases.create_task import CreateTaskUseCase
from application.use_cases.execute_task import ExecuteTaskUseCase
from domain.entities.task import SubTask
from domain.ports.llm_gateway import LLMResponse
from domain.value_objects.status import SubTaskStatus, TaskStatus
from infrastructure.persistence.in_memory import InMemoryTaskRepository
from infrastructure.task_graph.engine import LangGraphTaskEngine
from infrastructure.task_graph.intent_analyzer import IntentAnalyzer


def _mock_llm(**overrides) -> AsyncMock:
    """Create a mock LLMGateway."""
    llm = AsyncMock()
    llm.complete = AsyncMock(
        return_value=LLMResponse(
            content="result",
            model="mock-model",
            prompt_tokens=10,
            completion_tokens=20,
            cost_usd=0.0,
        )
    )
    llm.is_available = AsyncMock(return_value=True)
    llm.list_models = AsyncMock(return_value=["mock-model"])
    for k, v in overrides.items():
        setattr(llm, k, v)
    return llm


def _mock_analyzer(subtasks: list[SubTask]) -> AsyncMock:
    """Create a mock IntentAnalyzer that returns predefined subtasks."""
    analyzer = AsyncMock(spec=IntentAnalyzer)
    analyzer.decompose = AsyncMock(return_value=subtasks)
    return analyzer


class TestFailureRecoveryRetry:
    """Subtask failure → automatic retry → eventual success."""

    async def test_retry_then_succeed(self) -> None:
        """LLM fails on first call, succeeds on retry → overall SUCCESS."""
        call_count = 0

        async def flaky_complete(messages, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Temporary LLM failure")
            return LLMResponse(
                content="recovered result",
                model="mock-model",
                prompt_tokens=10,
                completion_tokens=20,
                cost_usd=0.001,
            )

        llm = _mock_llm()
        llm.complete = AsyncMock(side_effect=flaky_complete)

        subtasks = [SubTask(description="task A")]
        analyzer = _mock_analyzer(subtasks)
        engine = LangGraphTaskEngine(llm=llm, analyzer=analyzer)
        repo = InMemoryTaskRepository()

        create_uc = CreateTaskUseCase(engine=engine, repo=repo)
        task = await create_uc.execute("test goal")
        assert task.status == TaskStatus.PENDING

        execute_uc = ExecuteTaskUseCase(engine=engine, repo=repo)
        result = await execute_uc.execute(task.id)

        # Retry succeeded
        assert result.status == TaskStatus.SUCCESS
        assert result.success_rate == 1.0
        assert result.subtasks[0].status == SubTaskStatus.SUCCESS
        assert result.subtasks[0].result == "recovered result"
        # LLM was called twice: fail + retry
        assert call_count == 2

    async def test_retry_exhausted_then_fail(self) -> None:
        """LLM fails on all attempts → subtask FAILED → task FAILED."""
        llm = _mock_llm()
        llm.complete = AsyncMock(side_effect=RuntimeError("Persistent failure"))

        subtasks = [SubTask(description="doomed task")]
        analyzer = _mock_analyzer(subtasks)
        engine = LangGraphTaskEngine(llm=llm, analyzer=analyzer)
        repo = InMemoryTaskRepository()

        create_uc = CreateTaskUseCase(engine=engine, repo=repo)
        task = await create_uc.execute("fail goal")

        execute_uc = ExecuteTaskUseCase(engine=engine, repo=repo)
        result = await execute_uc.execute(task.id)

        assert result.status == TaskStatus.FAILED
        assert result.success_rate == 0.0
        assert result.subtasks[0].status == SubTaskStatus.FAILED
        assert result.subtasks[0].error is not None
        assert "Persistent failure" in result.subtasks[0].error
        # Should have been called MAX_RETRIES(2) times
        assert llm.complete.call_count == LangGraphTaskEngine.MAX_RETRIES


class TestFailureRecoveryPartialSuccess:
    """Some subtasks succeed, some fail → FALLBACK status."""

    async def test_partial_success_fallback(self) -> None:
        """2 independent subtasks: one succeeds, one fails → FALLBACK."""
        call_count = 0

        async def selective_fail(messages, **kwargs):
            nonlocal call_count
            call_count += 1
            user_msg = messages[-1]["content"]
            if "fail" in user_msg.lower():
                raise RuntimeError("Intentional failure")
            return LLMResponse(
                content="success result",
                model="mock-model",
                prompt_tokens=10,
                completion_tokens=20,
                cost_usd=0.001,
            )

        llm = _mock_llm()
        llm.complete = AsyncMock(side_effect=selective_fail)

        subtasks = [
            SubTask(id="a", description="Succeed task"),
            SubTask(id="b", description="Fail this task"),
        ]
        analyzer = _mock_analyzer(subtasks)
        engine = LangGraphTaskEngine(llm=llm, analyzer=analyzer)
        repo = InMemoryTaskRepository()

        create_uc = CreateTaskUseCase(engine=engine, repo=repo)
        task = await create_uc.execute("mixed goal")

        execute_uc = ExecuteTaskUseCase(engine=engine, repo=repo)
        result = await execute_uc.execute(task.id)

        assert result.status == TaskStatus.FALLBACK
        assert 0 < result.success_rate < 1.0

        statuses = {s.id: s.status for s in result.subtasks}
        assert statuses["a"] == SubTaskStatus.SUCCESS
        assert statuses["b"] == SubTaskStatus.FAILED


class TestFailureRecoveryDependencyBlocking:
    """Dependent subtask blocked by failed parent → cascading failure."""

    async def test_dependency_cascade_failure(self) -> None:
        """A fails → B (depends on A) is blocked and marked FAILED."""
        llm = _mock_llm()
        llm.complete = AsyncMock(side_effect=RuntimeError("A fails"))

        subtasks = [
            SubTask(id="a", description="task A"),
            SubTask(id="b", description="task B", dependencies=["a"]),
        ]
        analyzer = _mock_analyzer(subtasks)
        engine = LangGraphTaskEngine(llm=llm, analyzer=analyzer)
        repo = InMemoryTaskRepository()

        create_uc = CreateTaskUseCase(engine=engine, repo=repo)
        task = await create_uc.execute("chained goal")

        execute_uc = ExecuteTaskUseCase(engine=engine, repo=repo)
        result = await execute_uc.execute(task.id)

        assert result.status == TaskStatus.FAILED
        assert result.success_rate == 0.0

        a = next(s for s in result.subtasks if s.id == "a")
        b = next(s for s in result.subtasks if s.id == "b")
        assert a.status == SubTaskStatus.FAILED
        assert b.status == SubTaskStatus.FAILED
        assert "dependency" in (b.error or "").lower() or "blocked" in (b.error or "").lower()

    async def test_dependency_chain_success_then_fail(self) -> None:
        """A succeeds → B (depends on A) fails → task FALLBACK."""
        call_count = 0

        async def chain_behavior(messages, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                # First call: A succeeds
                return LLMResponse(
                    content="A done",
                    model="mock-model",
                    prompt_tokens=10,
                    completion_tokens=20,
                    cost_usd=0.0,
                )
            # Subsequent calls: B fails
            raise RuntimeError("B fails")

        llm = _mock_llm()
        llm.complete = AsyncMock(side_effect=chain_behavior)

        subtasks = [
            SubTask(id="a", description="task A"),
            SubTask(id="b", description="task B", dependencies=["a"]),
        ]
        analyzer = _mock_analyzer(subtasks)
        engine = LangGraphTaskEngine(llm=llm, analyzer=analyzer)
        repo = InMemoryTaskRepository()

        create_uc = CreateTaskUseCase(engine=engine, repo=repo)
        task = await create_uc.execute("chain goal")

        execute_uc = ExecuteTaskUseCase(engine=engine, repo=repo)
        result = await execute_uc.execute(task.id)

        assert result.status == TaskStatus.FALLBACK
        assert result.success_rate == 0.5

        a = next(s for s in result.subtasks if s.id == "a")
        b = next(s for s in result.subtasks if s.id == "b")
        assert a.status == SubTaskStatus.SUCCESS
        assert b.status == SubTaskStatus.FAILED


class TestFailureRecoveryPersistence:
    """Failure state is correctly persisted."""

    async def test_failed_state_persisted(self) -> None:
        """After failure, repository contains the failed task state."""
        llm = _mock_llm()
        llm.complete = AsyncMock(side_effect=RuntimeError("always fails"))

        subtasks = [SubTask(description="will fail")]
        analyzer = _mock_analyzer(subtasks)
        engine = LangGraphTaskEngine(llm=llm, analyzer=analyzer)
        repo = InMemoryTaskRepository()

        create_uc = CreateTaskUseCase(engine=engine, repo=repo)
        task = await create_uc.execute("persist fail")

        execute_uc = ExecuteTaskUseCase(engine=engine, repo=repo)
        await execute_uc.execute(task.id)

        # Verify persisted state
        stored = await repo.get_by_id(task.id)
        assert stored is not None
        assert stored.status == TaskStatus.FAILED
        assert stored.is_complete is True
        assert stored.subtasks[0].status == SubTaskStatus.FAILED
        assert stored.subtasks[0].error is not None

    async def test_retry_success_persisted(self) -> None:
        """After retry success, repository contains the recovered state."""
        call_count = 0

        async def flaky(messages, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient")
            return LLMResponse(
                content="recovered",
                model="mock-model",
                prompt_tokens=10,
                completion_tokens=20,
                cost_usd=0.0,
            )

        llm = _mock_llm()
        llm.complete = AsyncMock(side_effect=flaky)

        subtasks = [SubTask(description="recoverable")]
        analyzer = _mock_analyzer(subtasks)
        engine = LangGraphTaskEngine(llm=llm, analyzer=analyzer)
        repo = InMemoryTaskRepository()

        create_uc = CreateTaskUseCase(engine=engine, repo=repo)
        task = await create_uc.execute("persist recover")

        execute_uc = ExecuteTaskUseCase(engine=engine, repo=repo)
        await execute_uc.execute(task.id)

        stored = await repo.get_by_id(task.id)
        assert stored is not None
        assert stored.status == TaskStatus.SUCCESS
        assert stored.subtasks[0].result == "recovered"
