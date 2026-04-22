"""TDD: IntentAnalyzer artifact flow — Sprint 13.4a + TD-096 dependency inference."""

import json

from domain.entities.task import SubTask
from domain.value_objects.model_preference import CollaborationMode, ModelPreference
from infrastructure.task_graph.intent_analyzer import IntentAnalyzer


class TestParseResponseArtifacts:
    """_parse_response extracts produces/consumes from LLM JSON."""

    def test_llm_specified_artifacts(self):
        content = json.dumps(
            [
                {
                    "description": "Search the web",
                    "produces": ["search_results"],
                    "consumes": [],
                    "deps": [],
                },
                {
                    "description": "Analyze results",
                    "produces": ["analysis"],
                    "consumes": ["search_results"],
                    "deps": [0],
                },
            ]
        )
        subtasks = IntentAnalyzer._parse_response(content)
        assert len(subtasks) == 2

        # First subtask produces, doesn't consume
        assert "search_results" in subtasks[0].output_artifacts
        assert subtasks[0].input_artifacts == {}

        # Second subtask consumes search_results, produces analysis
        assert "search_results" in subtasks[1].input_artifacts
        assert "analysis" in subtasks[1].output_artifacts

    def test_no_artifacts_preserves_llm_deps(self):
        """TD-159: When LLM provides deps but no artifacts, LLM deps are
        preserved — no linear chain override.  Artifacts stay empty."""
        content = json.dumps(
            [
                {"description": "Step one", "deps": []},
                {"description": "Step two", "deps": [0]},
                {"description": "Step three", "deps": [1]},
            ]
        )
        subtasks = IntentAnalyzer._parse_response(content)
        assert len(subtasks) == 3

        # No artifact inference for LLM-decomposed subtasks
        assert subtasks[0].output_artifacts == {}
        assert subtasks[1].output_artifacts == {}
        assert subtasks[2].output_artifacts == {}

        # LLM deps preserved exactly
        assert subtasks[0].dependencies == []
        assert subtasks[1].dependencies == [subtasks[0].id]
        assert subtasks[2].dependencies == [subtasks[1].id]

    def test_no_artifacts_parallel_deps_preserved(self):
        """TD-159: When LLM returns deps=[] (parallel), don't override
        with linear chain — all subtasks remain independent."""
        content = json.dumps(
            [
                {"description": "Step one", "deps": []},
                {"description": "Step two", "deps": []},
                {"description": "Step three", "deps": []},
            ]
        )
        subtasks = IntentAnalyzer._parse_response(content)
        assert len(subtasks) == 3

        # All independent (parallel) — LLM's intent preserved
        assert subtasks[0].dependencies == []
        assert subtasks[1].dependencies == []
        assert subtasks[2].dependencies == []

    def test_single_subtask_produces_only(self):
        """Single subtask gets output_artifacts but no input_artifacts."""
        content = json.dumps([{"description": "Do it", "deps": []}])
        subtasks = IntentAnalyzer._parse_response(content)
        assert len(subtasks) == 1
        # Single subtask: no linear chain needed
        assert subtasks[0].input_artifacts == {}
        assert subtasks[0].output_artifacts == {}

    def test_partial_artifacts_uses_llm_specified(self):
        """If even one subtask has produces/consumes, use LLM-specified flow."""
        content = json.dumps(
            [
                {"description": "A", "produces": ["data"], "deps": []},
                {"description": "B", "deps": [0]},  # no produces/consumes
            ]
        )
        subtasks = IntentAnalyzer._parse_response(content)
        assert "data" in subtasks[0].output_artifacts
        # B has no LLM-specified artifacts — stays empty (not inferred)
        assert subtasks[1].output_artifacts == {}
        assert subtasks[1].input_artifacts == {}


class TestParseMultiModelArtifacts:
    """_parse_multi_model_response with artifact fields."""

    def test_multi_model_with_artifacts(self):
        allowed = ("claude-sonnet-4-6", "gemini/gemini-2.5-flash")
        content = json.dumps(
            [
                {
                    "description": "Search with Gemini",
                    "model": "gemini/gemini-2.5-flash",
                    "produces": ["web_data"],
                    "consumes": [],
                    "deps": [],
                },
                {
                    "description": "Analyze with Claude",
                    "model": "claude-sonnet-4-6",
                    "produces": ["analysis"],
                    "consumes": ["web_data"],
                    "deps": [0],
                },
            ]
        )
        subtasks = IntentAnalyzer._parse_multi_model_response(content, allowed)
        assert len(subtasks) == 2
        assert "web_data" in subtasks[0].output_artifacts
        assert "web_data" in subtasks[1].input_artifacts
        assert "analysis" in subtasks[1].output_artifacts

    def test_multi_model_no_artifacts_preserves_deps(self):
        """TD-159: LLM deps preserved, no linear artifact chain override."""
        allowed = ("model-a", "model-b")
        content = json.dumps(
            [
                {"description": "A task", "model": "model-a", "deps": []},
                {"description": "B task", "model": "model-b", "deps": [0]},
            ]
        )
        subtasks = IntentAnalyzer._parse_multi_model_response(content, allowed)
        # No artifact inference — LLM deps preserved
        assert subtasks[0].output_artifacts == {}
        assert subtasks[1].output_artifacts == {}
        assert subtasks[0].dependencies == []
        assert subtasks[0].id in subtasks[1].dependencies

    def test_multi_model_no_deps_infers_from_artifacts(self):
        """TD-096: When LLM provides produces/consumes but no deps,
        dependencies are inferred from artifact flow."""
        allowed = ("gemini/gemini-2.5-flash", "claude-sonnet-4-6")
        content = json.dumps(
            [
                {
                    "description": "Search",
                    "model": "gemini/gemini-2.5-flash",
                    "produces": ["search_results"],
                    "consumes": [],
                    "deps": [],
                },
                {
                    "description": "Analyze",
                    "model": "claude-sonnet-4-6",
                    "produces": ["report"],
                    "consumes": ["search_results"],
                    "deps": [],  # LLM forgot to set deps
                },
            ]
        )
        subtasks = IntentAnalyzer._parse_multi_model_response(content, allowed)
        # Dependency inferred from artifact flow: B consumes what A produces
        assert subtasks[0].id in subtasks[1].dependencies

    def test_multi_model_parallel_deps_preserved(self):
        """TD-159: When LLM returns deps=[] for all subtasks, parallel
        structure is preserved — no linear chain override."""
        allowed = ("model-a", "model-b", "model-c")
        content = json.dumps(
            [
                {"description": "Task A", "model": "model-a", "deps": []},
                {"description": "Task B", "model": "model-b", "deps": []},
                {"description": "Task C", "model": "model-c", "deps": []},
            ]
        )
        subtasks = IntentAnalyzer._parse_multi_model_response(content, allowed)

        # All parallel — LLM's intent preserved
        assert subtasks[0].dependencies == []
        assert subtasks[1].dependencies == []
        assert subtasks[2].dependencies == []

        # No artifacts inferred for LLM-decomposed path
        assert subtasks[0].output_artifacts == {}
        assert subtasks[1].output_artifacts == {}
        assert subtasks[2].output_artifacts == {}


class TestApplyArtifactFlow:
    """_apply_artifact_flow static method."""

    def test_llm_specified_flow(self):
        subtasks = [
            SubTask(description="A"),
            SubTask(description="B"),
        ]
        produces = {0: ["data"], 1: ["report"]}
        consumes = {0: [], 1: ["data"]}

        IntentAnalyzer._apply_artifact_flow(subtasks, produces, consumes)

        assert subtasks[0].output_artifacts == {"data": ""}
        assert subtasks[0].input_artifacts == {}
        assert subtasks[1].output_artifacts == {"report": ""}
        assert subtasks[1].input_artifacts == {"data": ""}

    def test_llm_specified_flow_infers_deps(self):
        """TD-096: Dependencies inferred from produces/consumes relationship."""
        subtasks = [
            SubTask(description="Producer"),
            SubTask(description="Consumer"),
        ]
        produces = {0: ["data"], 1: ["report"]}
        consumes = {0: [], 1: ["data"]}

        IntentAnalyzer._apply_artifact_flow(subtasks, produces, consumes)

        # Consumer depends on producer
        assert subtasks[0].dependencies == []
        assert subtasks[0].id in subtasks[1].dependencies

    def test_llm_specified_flow_no_duplicate_deps(self):
        """TD-096: Don't add duplicate dependencies."""
        a = SubTask(description="A")
        b = SubTask(description="B", dependencies=[a.id])  # already depends on A
        subtasks = [a, b]
        produces = {0: ["data"], 1: []}
        consumes = {0: [], 1: ["data"]}

        IntentAnalyzer._apply_artifact_flow(subtasks, produces, consumes)

        # Should NOT duplicate
        assert subtasks[1].dependencies.count(a.id) == 1

    def test_llm_specified_flow_multi_producer(self):
        """TD-096: Consumer can depend on multiple producers."""
        subtasks = [
            SubTask(description="A"),
            SubTask(description="B"),
            SubTask(description="C"),
        ]
        produces = {0: ["data_a"], 1: ["data_b"], 2: []}
        consumes = {0: [], 1: [], 2: ["data_a", "data_b"]}

        IntentAnalyzer._apply_artifact_flow(subtasks, produces, consumes)

        # C depends on both A and B
        assert subtasks[0].id in subtasks[2].dependencies
        assert subtasks[1].id in subtasks[2].dependencies
        assert subtasks[0].dependencies == []
        assert subtasks[1].dependencies == []

    def test_inferred_linear_chain(self):
        subtasks = [
            SubTask(description="A"),
            SubTask(description="B"),
        ]
        produces: dict[int, list[str]] = {0: [], 1: []}
        consumes: dict[int, list[str]] = {0: [], 1: []}

        IntentAnalyzer._apply_artifact_flow(subtasks, produces, consumes)

        assert subtasks[0].output_artifacts == {"step_0_output": ""}
        assert subtasks[0].input_artifacts == {}
        assert subtasks[1].output_artifacts == {"step_1_output": ""}
        assert subtasks[1].input_artifacts == {"step_0_output": ""}

    def test_inferred_linear_chain_sets_deps(self):
        """TD-096: Linear chain inference also sets dependencies."""
        subtasks = [
            SubTask(description="A"),
            SubTask(description="B"),
            SubTask(description="C"),
        ]
        produces: dict[int, list[str]] = {}
        consumes: dict[int, list[str]] = {}

        IntentAnalyzer._apply_artifact_flow(subtasks, produces, consumes)

        assert subtasks[0].dependencies == []
        assert subtasks[0].id in subtasks[1].dependencies
        assert subtasks[1].id in subtasks[2].dependencies

    def test_inferred_chain_no_duplicate_deps(self):
        """TD-096: Don't duplicate deps that already exist."""
        a = SubTask(description="A")
        b = SubTask(description="B", dependencies=[a.id])
        subtasks = [a, b]
        produces: dict[int, list[str]] = {}
        consumes: dict[int, list[str]] = {}

        IntentAnalyzer._apply_artifact_flow(subtasks, produces, consumes)

        assert subtasks[1].dependencies.count(a.id) == 1

    def test_single_subtask_no_chain(self):
        subtasks = [SubTask(description="only")]
        IntentAnalyzer._apply_artifact_flow(subtasks, {0: []}, {0: []})
        assert subtasks[0].output_artifacts == {}
        assert subtasks[0].input_artifacts == {}


class TestCreatePerModelSubtasks:
    """TD-096: Static fallback now creates artifact chain and dependencies."""

    def test_two_models_creates_chain(self):
        preference = ModelPreference(
            models=("model-a", "model-b"),
            clean_goal="analyze data",
            collaboration_mode=CollaborationMode.AUTO,
        )
        subtasks = IntentAnalyzer._create_per_model_subtasks(preference)
        assert len(subtasks) == 2

        # Artifacts: linear chain
        assert "step_0_output" in subtasks[0].output_artifacts
        assert "step_0_output" in subtasks[1].input_artifacts

        # Dependencies: B depends on A
        assert subtasks[0].dependencies == []
        assert subtasks[0].id in subtasks[1].dependencies

    def test_three_models_creates_chain(self):
        preference = ModelPreference(
            models=("model-a", "model-b", "model-c"),
            clean_goal="do something",
            collaboration_mode=CollaborationMode.PARALLEL,
        )
        subtasks = IntentAnalyzer._create_per_model_subtasks(preference)
        assert len(subtasks) == 3

        # A → B → C chain
        assert subtasks[0].dependencies == []
        assert subtasks[0].id in subtasks[1].dependencies
        assert subtasks[1].id in subtasks[2].dependencies

    def test_single_model_no_chain(self):
        preference = ModelPreference(
            models=("model-a",),
            clean_goal="solo task",
            collaboration_mode=CollaborationMode.AUTO,
        )
        subtasks = IntentAnalyzer._create_per_model_subtasks(preference)
        assert len(subtasks) == 1
        assert subtasks[0].dependencies == []
        assert subtasks[0].output_artifacts == {}
        assert subtasks[0].input_artifacts == {}

    def test_preferred_model_preserved(self):
        preference = ModelPreference(
            models=("claude-sonnet-4-6", "gemini/gemini-2.5-flash"),
            clean_goal="task",
            collaboration_mode=CollaborationMode.AUTO,
        )
        subtasks = IntentAnalyzer._create_per_model_subtasks(preference)
        assert subtasks[0].preferred_model == "claude-sonnet-4-6"
        assert subtasks[1].preferred_model == "gemini/gemini-2.5-flash"
