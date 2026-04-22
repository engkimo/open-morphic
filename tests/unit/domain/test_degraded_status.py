"""Tests for DEGRADED status, tools_used, data_sources fields (Sprint 12.1+12.5)."""

from domain.entities.task import SubTask, TaskEntity
from domain.value_objects.status import SubTaskStatus


class TestSubTaskDegradedStatus:
    def test_degraded_value(self) -> None:
        assert SubTaskStatus.DEGRADED == "degraded"

    def test_subtask_with_degraded(self) -> None:
        st = SubTask(description="Search for tickets", status=SubTaskStatus.DEGRADED)
        assert st.status == SubTaskStatus.DEGRADED

    def test_degraded_is_terminal(self) -> None:
        """DEGRADED should count as a terminal state for is_complete."""
        task = TaskEntity(
            goal="Find tickets",
            subtasks=[SubTask(description="Search", status=SubTaskStatus.DEGRADED)],
        )
        assert task.is_complete

    def test_degraded_counts_in_success_rate(self) -> None:
        """DEGRADED counts as partial success for success_rate."""
        task = TaskEntity(
            goal="Multi task",
            subtasks=[
                SubTask(description="A", status=SubTaskStatus.SUCCESS),
                SubTask(description="B", status=SubTaskStatus.DEGRADED),
            ],
        )
        assert task.success_rate == 1.0

    def test_degraded_satisfies_dependencies(self) -> None:
        """DEGRADED subtask should satisfy dependency for downstream subtasks."""
        st_a = SubTask(description="A", status=SubTaskStatus.DEGRADED)
        st_b = SubTask(description="B", dependencies=[st_a.id])
        task = TaskEntity(goal="Test", subtasks=[st_a, st_b])
        ready = task.get_ready_subtasks()
        assert len(ready) == 1
        assert ready[0].id == st_b.id


class TestSubTaskToolsUsed:
    def test_default_empty(self) -> None:
        st = SubTask(description="task")
        assert st.tools_used == []

    def test_set_tools_used(self) -> None:
        st = SubTask(description="task", tools_used=["web_search", "web_fetch"])
        assert st.tools_used == ["web_search", "web_fetch"]


class TestSubTaskDataSources:
    def test_default_empty(self) -> None:
        st = SubTask(description="task")
        assert st.data_sources == []

    def test_set_data_sources(self) -> None:
        st = SubTask(
            description="task",
            data_sources=["https://example.com", "https://foo.bar"],
        )
        assert len(st.data_sources) == 2


class TestMixedStatusCompletion:
    def test_all_success_and_degraded(self) -> None:
        task = TaskEntity(
            goal="Mixed",
            subtasks=[
                SubTask(description="A", status=SubTaskStatus.SUCCESS),
                SubTask(description="B", status=SubTaskStatus.DEGRADED),
                SubTask(description="C", status=SubTaskStatus.FAILED),
            ],
        )
        assert task.is_complete
        assert abs(task.success_rate - 2 / 3) < 0.01

    def test_pending_not_complete(self) -> None:
        task = TaskEntity(
            goal="Pending",
            subtasks=[
                SubTask(description="A", status=SubTaskStatus.DEGRADED),
                SubTask(description="B", status=SubTaskStatus.PENDING),
            ],
        )
        assert not task.is_complete
