"""Tests for Skill Acquisition Loop — Plan C.

Verifies that ExecuteTaskUseCase:
- Discovers tools on failure
- Installs safe candidates (>= COMMUNITY)
- Retries task execution after successful installation
- Handles missing dependencies gracefully
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from application.use_cases.discover_tools import DiscoverToolsUseCase, ToolSuggestions
from application.use_cases.execute_task import ExecuteTaskUseCase
from application.use_cases.install_tool import InstallToolUseCase
from domain.entities.task import SubTask, TaskEntity
from domain.entities.tool_candidate import ToolCandidate
from domain.ports.task_engine import TaskEngine
from domain.ports.task_repository import TaskRepository
from domain.ports.tool_installer import InstallResult
from domain.value_objects.status import SubTaskStatus, TaskStatus
from domain.value_objects.tool_safety import SafetyTier


def _make_task(
    *statuses: SubTaskStatus,
    goal: str = "Create a presentation",
    error: str | None = "FileNotFoundError: python-pptx not installed",
) -> TaskEntity:
    subtasks = []
    for i, st in enumerate(statuses):
        s = SubTask(description=f"Step {i + 1}")
        s.status = st
        s.cost_usd = 0.01
        if st == SubTaskStatus.FAILED:
            s.error = error
        subtasks.append(s)
    return TaskEntity(goal=goal, subtasks=subtasks)


def _candidate(
    name: str = "python-pptx",
    safety: SafetyTier = SafetyTier.VERIFIED,
) -> ToolCandidate:
    return ToolCandidate(name=name, safety_tier=safety, safety_score=0.9)


@pytest.fixture
def engine() -> AsyncMock:
    return AsyncMock(spec=TaskEngine)


@pytest.fixture
def repo() -> AsyncMock:
    return AsyncMock(spec=TaskRepository)


@pytest.fixture
def discover() -> AsyncMock:
    return AsyncMock(spec=DiscoverToolsUseCase)


@pytest.fixture
def installer() -> AsyncMock:
    return AsyncMock(spec=InstallToolUseCase)


class TestSkillAcquisition:
    async def test_acquire_and_retry_on_failure(
        self, engine, repo, discover, installer
    ):
        """Full flow: fail → discover → install → retry → succeed."""
        failed_task = _make_task(SubTaskStatus.FAILED)
        success_task = _make_task(SubTaskStatus.SUCCESS)

        repo.get_by_id.return_value = failed_task
        # First execute fails, second succeeds
        engine.execute.side_effect = [failed_task, success_task]

        discover.suggest_for_failure.return_value = ToolSuggestions(
            suggestions=[_candidate()],
            queries_used=["python-pptx"],
        )
        installer.install.return_value = InstallResult(
            tool_name="python-pptx", success=True, message="Installed"
        )

        uc = ExecuteTaskUseCase(
            engine=engine,
            repo=repo,
            discover_tools=discover,
            install_tool=installer,
            max_skill_retries=1,
        )
        result = await uc.execute(failed_task.id)

        # Should have retried
        assert engine.execute.call_count == 2
        assert result.status == TaskStatus.SUCCESS

    async def test_no_retry_when_no_discover(self, engine, repo):
        """Without discover_tools, no retry happens."""
        failed_task = _make_task(SubTaskStatus.FAILED)
        repo.get_by_id.return_value = failed_task
        engine.execute.return_value = failed_task

        uc = ExecuteTaskUseCase(engine=engine, repo=repo, max_skill_retries=1)
        result = await uc.execute(failed_task.id)

        assert engine.execute.call_count == 1
        assert result.status == TaskStatus.FAILED

    async def test_no_retry_when_no_installer(self, engine, repo, discover):
        """With discover but no installer, log only (no retry)."""
        failed_task = _make_task(SubTaskStatus.FAILED)
        repo.get_by_id.return_value = failed_task
        engine.execute.return_value = failed_task

        discover.suggest_for_failure.return_value = ToolSuggestions(
            suggestions=[_candidate()],
            queries_used=["python-pptx"],
        )

        uc = ExecuteTaskUseCase(
            engine=engine, repo=repo, discover_tools=discover, max_skill_retries=1,
        )
        _result = await uc.execute(failed_task.id)

        assert engine.execute.call_count == 1

    async def test_no_retry_when_no_safe_candidates(
        self, engine, repo, discover, installer
    ):
        """Only COMMUNITY+ candidates are installed."""
        failed_task = _make_task(SubTaskStatus.FAILED)
        repo.get_by_id.return_value = failed_task
        engine.execute.return_value = failed_task

        # Only EXPERIMENTAL candidates
        discover.suggest_for_failure.return_value = ToolSuggestions(
            suggestions=[_candidate(safety=SafetyTier.EXPERIMENTAL)],
            queries_used=["risky-tool"],
        )

        uc = ExecuteTaskUseCase(
            engine=engine, repo=repo,
            discover_tools=discover, install_tool=installer,
            max_skill_retries=1,
        )
        _result = await uc.execute(failed_task.id)

        installer.install.assert_not_called()
        assert engine.execute.call_count == 1

    async def test_no_retry_when_install_fails(
        self, engine, repo, discover, installer
    ):
        """If installation fails, don't retry."""
        failed_task = _make_task(SubTaskStatus.FAILED)
        repo.get_by_id.return_value = failed_task
        engine.execute.return_value = failed_task

        discover.suggest_for_failure.return_value = ToolSuggestions(
            suggestions=[_candidate()],
            queries_used=["python-pptx"],
        )
        installer.install.return_value = InstallResult(
            tool_name="python-pptx", success=False, message="Install error"
        )

        uc = ExecuteTaskUseCase(
            engine=engine, repo=repo,
            discover_tools=discover, install_tool=installer,
            max_skill_retries=1,
        )
        _result = await uc.execute(failed_task.id)

        assert engine.execute.call_count == 1

    async def test_no_retry_when_no_suggestions(
        self, engine, repo, discover, installer
    ):
        """If no tool suggestions, don't retry."""
        failed_task = _make_task(SubTaskStatus.FAILED)
        repo.get_by_id.return_value = failed_task
        engine.execute.return_value = failed_task

        discover.suggest_for_failure.return_value = ToolSuggestions(
            suggestions=[], queries_used=[],
        )

        uc = ExecuteTaskUseCase(
            engine=engine, repo=repo,
            discover_tools=discover, install_tool=installer,
            max_skill_retries=1,
        )
        _result = await uc.execute(failed_task.id)

        installer.install.assert_not_called()
        assert engine.execute.call_count == 1

    async def test_no_retry_when_max_retries_zero(
        self, engine, repo, discover, installer
    ):
        """max_skill_retries=0 disables the retry loop."""
        failed_task = _make_task(SubTaskStatus.FAILED)
        repo.get_by_id.return_value = failed_task
        engine.execute.return_value = failed_task

        discover.suggest_for_failure.return_value = ToolSuggestions(
            suggestions=[_candidate()],
            queries_used=["python-pptx"],
        )
        installer.install.return_value = InstallResult(
            tool_name="python-pptx", success=True, message="OK"
        )

        uc = ExecuteTaskUseCase(
            engine=engine, repo=repo,
            discover_tools=discover, install_tool=installer,
            max_skill_retries=0,
        )
        _result = await uc.execute(failed_task.id)

        # Still tries to acquire, but skips the retry even if acquired
        assert engine.execute.call_count == 1

    async def test_acquire_skips_on_no_errors(
        self, engine, repo, discover, installer
    ):
        """If task failed but subtasks have no error strings, skip discovery."""
        failed_task = _make_task(SubTaskStatus.FAILED, error=None)
        repo.get_by_id.return_value = failed_task
        engine.execute.return_value = failed_task

        uc = ExecuteTaskUseCase(
            engine=engine, repo=repo,
            discover_tools=discover, install_tool=installer,
            max_skill_retries=1,
        )
        _result = await uc.execute(failed_task.id)

        discover.suggest_for_failure.assert_not_called()

    async def test_discover_exception_handled_gracefully(
        self, engine, repo, discover, installer
    ):
        """If discover_tools raises, execution continues without retry."""
        failed_task = _make_task(SubTaskStatus.FAILED)
        repo.get_by_id.return_value = failed_task
        engine.execute.return_value = failed_task

        discover.suggest_for_failure.side_effect = RuntimeError("Registry down")

        uc = ExecuteTaskUseCase(
            engine=engine, repo=repo,
            discover_tools=discover, install_tool=installer,
            max_skill_retries=1,
        )
        # Should not raise
        _result = await uc.execute(failed_task.id)
        assert engine.execute.call_count == 1
