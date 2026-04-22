"""TDD: Artifact fields on SubTask and PlanStep — Sprint 13.4a."""

from domain.entities.plan import PlanStep
from domain.entities.task import SubTask, TaskEntity
from domain.value_objects.status import SubTaskStatus


class TestSubTaskArtifacts:
    """SubTask input_artifacts / output_artifacts fields."""

    def test_default_empty(self):
        st = SubTask(description="step A")
        assert st.input_artifacts == {}
        assert st.output_artifacts == {}

    def test_set_input_artifacts(self):
        st = SubTask(
            description="analyze",
            input_artifacts={"search_results": "data from step 1"},
        )
        assert st.input_artifacts["search_results"] == "data from step 1"

    def test_set_output_artifacts(self):
        st = SubTask(
            description="search",
            output_artifacts={"search_results": ""},
        )
        assert "search_results" in st.output_artifacts

    def test_multiple_artifacts(self):
        st = SubTask(
            description="execute code",
            output_artifacts={"code": "print(1)", "exec_output": "1"},
        )
        assert len(st.output_artifacts) == 2
        assert st.output_artifacts["code"] == "print(1)"

    def test_artifacts_mutable(self):
        st = SubTask(description="step")
        st.output_artifacts = {"result": "done"}
        assert st.output_artifacts["result"] == "done"

    def test_artifacts_preserved_in_task(self):
        st = SubTask(
            description="step",
            output_artifacts={"data": "content"},
        )
        task = TaskEntity(goal="test", subtasks=[st])
        assert task.subtasks[0].output_artifacts["data"] == "content"

    def test_backward_compatible_no_artifacts(self):
        """Existing code creating SubTask without artifacts still works."""
        st = SubTask(
            id="abc",
            description="old style",
            status=SubTaskStatus.PENDING,
            dependencies=[],
            preferred_model="ollama/qwen3:8b",
        )
        assert st.input_artifacts == {}
        assert st.output_artifacts == {}


class TestPlanStepArtifacts:
    """PlanStep produces / consumes fields."""

    def test_default_empty(self):
        ps = PlanStep(subtask_description="step A")
        assert ps.produces == []
        assert ps.consumes == []

    def test_set_produces(self):
        ps = PlanStep(
            subtask_description="search the web",
            produces=["search_results", "urls"],
        )
        assert ps.produces == ["search_results", "urls"]

    def test_set_consumes(self):
        ps = PlanStep(
            subtask_description="analyze results",
            consumes=["search_results"],
        )
        assert ps.consumes == ["search_results"]

    def test_both_produces_and_consumes(self):
        ps = PlanStep(
            subtask_description="code analysis",
            produces=["analysis_report"],
            consumes=["search_results", "code"],
        )
        assert len(ps.produces) == 1
        assert len(ps.consumes) == 2

    def test_backward_compatible(self):
        """Existing PlanStep creation without artifact fields still works."""
        ps = PlanStep(
            subtask_description="old step",
            proposed_model="ollama/qwen3:8b",
            estimated_cost_usd=0.0,
            estimated_tokens=100,
        )
        assert ps.produces == []
        assert ps.consumes == []
