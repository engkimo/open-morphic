"""Tests for ExecuteTaskUseCase — task execution lifecycle."""

from unittest.mock import AsyncMock

import pytest

from application.use_cases.discover_tools import DiscoverToolsUseCase, ToolSuggestions
from application.use_cases.execute_task import ExecuteTaskUseCase, TaskNotFoundError
from application.use_cases.extract_insights import ExtractInsightsUseCase
from domain.entities.execution_record import ExecutionRecord
from domain.entities.task import SubTask, TaskEntity
from domain.entities.tool_candidate import ToolCandidate
from domain.ports.execution_record_repository import ExecutionRecordRepository
from domain.ports.task_engine import TaskEngine
from domain.ports.task_repository import TaskRepository
from domain.value_objects.model_tier import TaskType
from domain.value_objects.status import SubTaskStatus, TaskStatus


@pytest.fixture
def engine() -> AsyncMock:
    return AsyncMock(spec=TaskEngine)


@pytest.fixture
def repo() -> AsyncMock:
    return AsyncMock(spec=TaskRepository)


@pytest.fixture
def use_case(engine: AsyncMock, repo: AsyncMock) -> ExecuteTaskUseCase:
    return ExecuteTaskUseCase(engine, repo)


def _make_task(*subtask_statuses: SubTaskStatus) -> TaskEntity:
    """Create a task with subtasks in given statuses."""
    subtasks = []
    for i, status in enumerate(subtask_statuses):
        s = SubTask(description=f"Step {i + 1}")
        s.status = status
        s.cost_usd = 0.01
        subtasks.append(s)
    return TaskEntity(goal="Test goal", subtasks=subtasks)


class TestExecuteTask:
    async def test_success_when_all_subtasks_pass(
        self, use_case: ExecuteTaskUseCase, engine: AsyncMock, repo: AsyncMock
    ) -> None:
        task = _make_task(SubTaskStatus.SUCCESS, SubTaskStatus.SUCCESS)
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        result = await use_case.execute(task.id)

        assert result.status == TaskStatus.SUCCESS

    async def test_fallback_on_partial_success(
        self, use_case: ExecuteTaskUseCase, engine: AsyncMock, repo: AsyncMock
    ) -> None:
        task = _make_task(SubTaskStatus.SUCCESS, SubTaskStatus.FAILED)
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        result = await use_case.execute(task.id)

        assert result.status == TaskStatus.FALLBACK

    async def test_failed_when_all_subtasks_fail(
        self, use_case: ExecuteTaskUseCase, engine: AsyncMock, repo: AsyncMock
    ) -> None:
        task = _make_task(SubTaskStatus.FAILED, SubTaskStatus.FAILED)
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        result = await use_case.execute(task.id)

        assert result.status == TaskStatus.FAILED

    async def test_not_found_raises(self, use_case: ExecuteTaskUseCase, repo: AsyncMock) -> None:
        repo.get_by_id.return_value = None

        with pytest.raises(TaskNotFoundError) as exc_info:
            await use_case.execute("nonexistent-id")
        assert exc_info.value.task_id == "nonexistent-id"

    async def test_sets_running_before_execution(
        self, use_case: ExecuteTaskUseCase, engine: AsyncMock, repo: AsyncMock
    ) -> None:
        task = _make_task(SubTaskStatus.SUCCESS)
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        await use_case.execute(task.id)

        # repo.update called twice: once for RUNNING, once for final status
        assert repo.update.await_count == 2
        first_call_task = repo.update.call_args_list[0][0][0]
        assert first_call_task.status == TaskStatus.SUCCESS  # mutated in-place

    async def test_accumulates_total_cost(
        self, use_case: ExecuteTaskUseCase, engine: AsyncMock, repo: AsyncMock
    ) -> None:
        task = _make_task(SubTaskStatus.SUCCESS, SubTaskStatus.SUCCESS)
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        result = await use_case.execute(task.id)

        assert result.total_cost_usd == pytest.approx(0.02)


class TestExecuteTaskWithInsights:
    """Integration of insight extraction into ExecuteTaskUseCase."""

    @pytest.fixture
    def extract_uc(self) -> AsyncMock:
        return AsyncMock(spec=ExtractInsightsUseCase)

    @pytest.fixture
    def uc_with_insights(
        self, engine: AsyncMock, repo: AsyncMock, extract_uc: AsyncMock
    ) -> ExecuteTaskUseCase:
        return ExecuteTaskUseCase(engine, repo, extract_insights=extract_uc)

    async def test_calls_extract_after_execution(
        self,
        uc_with_insights: ExecuteTaskUseCase,
        engine: AsyncMock,
        repo: AsyncMock,
        extract_uc: AsyncMock,
    ) -> None:
        task = _make_task(SubTaskStatus.SUCCESS)
        task.subtasks[0].result = "uses PostgreSQL"
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        await uc_with_insights.execute(task.id)

        extract_uc.extract_and_store.assert_called_once()

    async def test_not_called_when_none(self, engine: AsyncMock, repo: AsyncMock) -> None:
        uc = ExecuteTaskUseCase(engine, repo, extract_insights=None)
        task = _make_task(SubTaskStatus.SUCCESS)
        task.subtasks[0].result = "something"
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        result = await uc.execute(task.id)
        assert result.status == TaskStatus.SUCCESS

    async def test_extraction_failure_does_not_block(
        self,
        uc_with_insights: ExecuteTaskUseCase,
        engine: AsyncMock,
        repo: AsyncMock,
        extract_uc: AsyncMock,
    ) -> None:
        task = _make_task(SubTaskStatus.SUCCESS)
        task.subtasks[0].result = "result text"
        repo.get_by_id.return_value = task
        engine.execute.return_value = task
        extract_uc.extract_and_store.side_effect = RuntimeError("boom")

        result = await uc_with_insights.execute(task.id)
        assert result.status == TaskStatus.SUCCESS

    async def test_receives_subtask_results(
        self,
        uc_with_insights: ExecuteTaskUseCase,
        engine: AsyncMock,
        repo: AsyncMock,
        extract_uc: AsyncMock,
    ) -> None:
        task = _make_task(SubTaskStatus.SUCCESS, SubTaskStatus.SUCCESS)
        task.subtasks[0].result = "result A"
        task.subtasks[1].result = "result B"
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        await uc_with_insights.execute(task.id)

        call_kwargs = extract_uc.extract_and_store.call_args
        output = (
            call_kwargs.kwargs.get("output") or call_kwargs[1].get("output") or call_kwargs[0][2]
        )
        assert "result A" in output
        assert "result B" in output

    async def test_receives_subtask_errors(
        self,
        uc_with_insights: ExecuteTaskUseCase,
        engine: AsyncMock,
        repo: AsyncMock,
        extract_uc: AsyncMock,
    ) -> None:
        task = _make_task(SubTaskStatus.FAILED)
        task.subtasks[0].error = "connection timeout"
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        await uc_with_insights.execute(task.id)

        call_kwargs = extract_uc.extract_and_store.call_args
        output = (
            call_kwargs.kwargs.get("output") or call_kwargs[1].get("output") or call_kwargs[0][2]
        )
        assert "connection timeout" in output


class TestExecuteTaskWithToolSuggestion:
    """Sprint 5.7b: auto-discovery triggered on task failure."""

    @pytest.fixture
    def discover_uc(self) -> AsyncMock:
        mock = AsyncMock(spec=DiscoverToolsUseCase)
        mock.suggest_for_failure = AsyncMock(
            return_value=ToolSuggestions(
                suggestions=[ToolCandidate(name="mcp-db-tool", safety_score=0.9)],
                queries_used=["database"],
            )
        )
        return mock

    @pytest.fixture
    def uc_with_discover(
        self, engine: AsyncMock, repo: AsyncMock, discover_uc: AsyncMock
    ) -> ExecuteTaskUseCase:
        return ExecuteTaskUseCase(engine, repo, discover_tools=discover_uc)

    async def test_suggests_tools_on_failure(
        self,
        uc_with_discover: ExecuteTaskUseCase,
        engine: AsyncMock,
        repo: AsyncMock,
        discover_uc: AsyncMock,
    ) -> None:
        task = _make_task(SubTaskStatus.FAILED)
        task.subtasks[0].error = "database connection refused"
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        await uc_with_discover.execute(task.id)

        discover_uc.suggest_for_failure.assert_called_once()

    async def test_not_called_on_success(
        self,
        uc_with_discover: ExecuteTaskUseCase,
        engine: AsyncMock,
        repo: AsyncMock,
        discover_uc: AsyncMock,
    ) -> None:
        task = _make_task(SubTaskStatus.SUCCESS)
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        await uc_with_discover.execute(task.id)

        discover_uc.suggest_for_failure.assert_not_called()

    async def test_called_on_fallback(
        self,
        engine: AsyncMock,
        repo: AsyncMock,
        discover_uc: AsyncMock,
    ) -> None:
        uc = ExecuteTaskUseCase(engine, repo, discover_tools=discover_uc)
        task = _make_task(SubTaskStatus.SUCCESS, SubTaskStatus.FAILED)
        task.subtasks[1].error = "timeout"
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        await uc.execute(task.id)

        discover_uc.suggest_for_failure.assert_called_once()

    async def test_failure_does_not_block(
        self,
        uc_with_discover: ExecuteTaskUseCase,
        engine: AsyncMock,
        repo: AsyncMock,
        discover_uc: AsyncMock,
    ) -> None:
        task = _make_task(SubTaskStatus.FAILED)
        task.subtasks[0].error = "some error"
        repo.get_by_id.return_value = task
        engine.execute.return_value = task
        discover_uc.suggest_for_failure.side_effect = RuntimeError("boom")

        result = await uc_with_discover.execute(task.id)

        assert result.status == TaskStatus.FAILED

    async def test_not_called_when_none(self, engine: AsyncMock, repo: AsyncMock) -> None:
        uc = ExecuteTaskUseCase(engine, repo, discover_tools=None)
        task = _make_task(SubTaskStatus.FAILED)
        task.subtasks[0].error = "error"
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        result = await uc.execute(task.id)
        assert result.status == TaskStatus.FAILED

    async def test_receives_combined_errors(
        self,
        engine: AsyncMock,
        repo: AsyncMock,
        discover_uc: AsyncMock,
    ) -> None:
        uc = ExecuteTaskUseCase(engine, repo, discover_tools=discover_uc)
        task = _make_task(SubTaskStatus.FAILED, SubTaskStatus.FAILED)
        task.subtasks[0].error = "error A"
        task.subtasks[1].error = "error B"
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        await uc.execute(task.id)

        call_args = discover_uc.suggest_for_failure.call_args
        error_msg = call_args.kwargs.get("error_message") or call_args[0][0]
        assert "error A" in error_msg
        assert "error B" in error_msg

    async def test_passes_task_goal(
        self,
        uc_with_discover: ExecuteTaskUseCase,
        engine: AsyncMock,
        repo: AsyncMock,
        discover_uc: AsyncMock,
    ) -> None:
        task = _make_task(SubTaskStatus.FAILED)
        task.subtasks[0].error = "some error"
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        await uc_with_discover.execute(task.id)

        call_args = discover_uc.suggest_for_failure.call_args
        desc = call_args.kwargs.get("task_description") or call_args[0][1]
        assert desc == "Test goal"

    async def test_skipped_when_no_errors(
        self,
        uc_with_discover: ExecuteTaskUseCase,
        engine: AsyncMock,
        repo: AsyncMock,
        discover_uc: AsyncMock,
    ) -> None:
        task = _make_task(SubTaskStatus.FAILED)
        # No .error set on subtask
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        await uc_with_discover.execute(task.id)

        discover_uc.suggest_for_failure.assert_not_called()


class TestExecuteTaskAutoRecording:
    """Self-evolution loop: auto-record ExecutionRecords after each task."""

    @pytest.fixture
    def record_repo(self) -> AsyncMock:
        return AsyncMock(spec=ExecutionRecordRepository)

    @pytest.fixture
    def uc_with_recording(
        self, engine: AsyncMock, repo: AsyncMock, record_repo: AsyncMock
    ) -> ExecuteTaskUseCase:
        return ExecuteTaskUseCase(
            engine, repo, execution_record_repo=record_repo, default_model="test-model"
        )

    async def test_auto_records_execution_on_success(
        self,
        uc_with_recording: ExecuteTaskUseCase,
        engine: AsyncMock,
        repo: AsyncMock,
        record_repo: AsyncMock,
    ) -> None:
        task = _make_task(SubTaskStatus.SUCCESS, SubTaskStatus.SUCCESS)
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        await uc_with_recording.execute(task.id)

        record_repo.save.assert_called_once()
        record: ExecutionRecord = record_repo.save.call_args[0][0]
        assert record.task_id == task.id
        assert record.success is True
        assert record.model_used == "test-model"
        assert record.cost_usd == pytest.approx(0.02)
        assert record.error_message is None

    async def test_auto_records_execution_on_failure(
        self,
        uc_with_recording: ExecuteTaskUseCase,
        engine: AsyncMock,
        repo: AsyncMock,
        record_repo: AsyncMock,
    ) -> None:
        task = _make_task(SubTaskStatus.FAILED)
        task.subtasks[0].error = "connection refused"
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        await uc_with_recording.execute(task.id)

        record: ExecutionRecord = record_repo.save.call_args[0][0]
        assert record.success is False
        assert record.error_message == "connection refused"

    async def test_auto_records_execution_on_fallback(
        self,
        uc_with_recording: ExecuteTaskUseCase,
        engine: AsyncMock,
        repo: AsyncMock,
        record_repo: AsyncMock,
    ) -> None:
        task = _make_task(SubTaskStatus.SUCCESS, SubTaskStatus.FAILED)
        task.subtasks[1].error = "partial failure"
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        await uc_with_recording.execute(task.id)

        record: ExecutionRecord = record_repo.save.call_args[0][0]
        assert record.success is False  # only full success counts
        assert record.error_message == "partial failure"

    async def test_recording_failure_does_not_block(
        self,
        uc_with_recording: ExecuteTaskUseCase,
        engine: AsyncMock,
        repo: AsyncMock,
        record_repo: AsyncMock,
    ) -> None:
        task = _make_task(SubTaskStatus.SUCCESS)
        repo.get_by_id.return_value = task
        engine.execute.return_value = task
        record_repo.save.side_effect = RuntimeError("DB down")

        result = await uc_with_recording.execute(task.id)

        assert result.status == TaskStatus.SUCCESS

    async def test_no_recording_when_repo_is_none(self, engine: AsyncMock, repo: AsyncMock) -> None:
        uc = ExecuteTaskUseCase(engine, repo, execution_record_repo=None)
        task = _make_task(SubTaskStatus.SUCCESS)
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        result = await uc.execute(task.id)

        assert result.status == TaskStatus.SUCCESS

    async def test_duration_is_positive(
        self,
        uc_with_recording: ExecuteTaskUseCase,
        engine: AsyncMock,
        repo: AsyncMock,
        record_repo: AsyncMock,
    ) -> None:
        task = _make_task(SubTaskStatus.SUCCESS)
        repo.get_by_id.return_value = task
        engine.execute.return_value = task

        await uc_with_recording.execute(task.id)

        record: ExecutionRecord = record_repo.save.call_args[0][0]
        assert record.duration_seconds >= 0.0

    async def test_task_type_inference(self) -> None:
        infer = ExecuteTaskUseCase._infer_task_type
        assert infer("Build a React frontend") == TaskType.CODE_GENERATION
        assert infer("Train a neural network") == TaskType.COMPLEX_REASONING
        assert infer("Deploy with Docker") == TaskType.FILE_OPERATION
        assert infer("Do something random") == TaskType.SIMPLE_QA
