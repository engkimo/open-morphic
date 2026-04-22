"""Tests for IntentAnalyzer — LLM-powered goal decomposition."""

import json
from unittest.mock import AsyncMock

import pytest

from domain.ports.llm_gateway import LLMGateway, LLMResponse
from infrastructure.task_graph.intent_analyzer import IntentAnalyzer

_GEMINI = "gemini/gemini-3-pro-preview"
_CLAUDE = "claude-sonnet-4-6"
_GPT = "o4-mini"


def _llm_response(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="ollama/qwen3:8b",
        prompt_tokens=50,
        completion_tokens=30,
        cost_usd=0.0,
    )


@pytest.fixture
def llm() -> AsyncMock:
    return AsyncMock(spec=LLMGateway)


@pytest.fixture
def analyzer(llm: AsyncMock) -> IntentAnalyzer:
    return IntentAnalyzer(llm)


class TestDecompose:
    async def test_decomposes_goal_into_subtasks(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "Write fibonacci function", "deps": []},
                    {"description": "Write unit tests", "deps": [0]},
                ]
            )
        )
        # Use a goal that classifies as MEDIUM/COMPLEX to trigger LLM path
        subtasks = await analyzer.decompose("Create a REST API endpoint with comprehensive tests")

        assert len(subtasks) == 2
        assert subtasks[0].description == "Write fibonacci function"
        assert subtasks[1].description == "Write unit tests"

    async def test_resolves_index_dependencies_to_ids(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "Configure authentication middleware", "deps": []},
                    {"description": "Build database migration scripts", "deps": [0]},
                    {"description": "Write integration tests for auth + DB", "deps": [0, 1]},
                ]
            )
        )
        subtasks = await analyzer.decompose(
            "Build a system with authentication, database, and testing"
        )

        assert subtasks[1].dependencies == [subtasks[0].id]
        assert subtasks[2].dependencies == [subtasks[0].id, subtasks[1].id]

    async def test_llm_parallel_deps_preserved(
        self,
        analyzer: IntentAnalyzer,
        llm: AsyncMock,
    ) -> None:
        """TD-159: When LLM returns deps=[] on independent subtasks,
        parallel structure is preserved — no linear chain override."""
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "Build frontend React components", "deps": []},
                    {"description": "Build backend API endpoints", "deps": []},
                ]
            )
        )
        subtasks = await analyzer.decompose(
            "Build frontend components and backend API endpoints together"
        )

        # Both subtasks should remain independent (parallel)
        assert subtasks[0].dependencies == []
        assert subtasks[1].dependencies == []

    async def test_invalid_json_raises(self, analyzer: IntentAnalyzer, llm: AsyncMock) -> None:
        llm.complete.return_value = _llm_response("not valid json")

        with pytest.raises(json.JSONDecodeError):
            # Use complex goal to trigger LLM path
            await analyzer.decompose("Build API with auth, database, and testing infrastructure")

    async def test_uses_low_temperature(self, analyzer: IntentAnalyzer, llm: AsyncMock) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps([{
                "description": "Initialize database schema and run migrations",
                "deps": [],
            }])
        )
        await analyzer.decompose("Create a REST API with database integration")

        call_kwargs = llm.complete.call_args[1]
        assert call_kwargs["temperature"] == 0.3

    async def test_ignores_invalid_dep_indices(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "Build frontend UI components with React", "deps": [99]},
                ]
            )
        )
        subtasks = await analyzer.decompose("Build a frontend UI and backend server together")

        assert subtasks[0].dependencies == []


class TestQualityGateAndTemplate:
    """TD-159: Quality gate for LLM decomposition + template fallback."""

    async def test_short_descriptions_trigger_template_fallback(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        """When LLM returns single-word descriptions, template is used instead."""
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "取得", "deps": []},
                    {"description": "解析", "deps": [0]},
                    {"description": "表示", "deps": [1]},
                ]
            )
        )
        subtasks = await analyzer.decompose(
            "Build a frontend UI and backend server together"
        )

        # Template should have replaced the bad LLM output
        assert all(len(st.description) >= 8 for st in subtasks)

    async def test_template_decomposition_medium_has_two_subtasks(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        """MEDIUM template produces 2 subtasks with dependency."""
        llm.complete.return_value = _llm_response(
            json.dumps([{"description": "Do", "deps": []}])
        )
        subtasks = await analyzer.decompose(
            "Create a REST API with database integration"
        )
        assert len(subtasks) == 2
        assert subtasks[0].dependencies == []
        assert subtasks[0].id in subtasks[1].dependencies

    async def test_template_complex_has_parallel_branches(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        """COMPLEX template produces parallel branches + synthesis."""
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "A", "deps": []},
                    {"description": "B", "deps": [0]},
                    {"description": "C", "deps": [1]},
                ]
            )
        )
        subtasks = await analyzer.decompose(
            "Build a system with authentication, database, and testing"
        )
        assert len(subtasks) == 3
        # First two are parallel (no deps)
        assert subtasks[0].dependencies == []
        assert subtasks[1].dependencies == []
        # Third depends on first two
        assert subtasks[0].id in subtasks[2].dependencies
        assert subtasks[1].id in subtasks[2].dependencies


class TestSimpleGoalSkipsLLM:
    """Sprint 9.1: SIMPLE goals should produce 1 subtask without LLM call."""

    async def test_simple_goal_returns_single_subtask(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        subtasks = await analyzer.decompose("FizzBuzz")

        assert len(subtasks) == 1
        assert subtasks[0].description == "FizzBuzz"

    async def test_simple_goal_does_not_call_llm(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        await analyzer.decompose("FizzBuzz")

        llm.complete.assert_not_called()

    async def test_fibonacci_is_simple(self, analyzer: IntentAnalyzer, llm: AsyncMock) -> None:
        subtasks = await analyzer.decompose("Implement fibonacci in Python")

        assert len(subtasks) == 1
        assert subtasks[0].description == "Implement fibonacci in Python"
        llm.complete.assert_not_called()

    async def test_fix_bug_is_simple(self, analyzer: IntentAnalyzer, llm: AsyncMock) -> None:
        subtasks = await analyzer.decompose("Fix the login bug")

        assert len(subtasks) == 1
        llm.complete.assert_not_called()

    async def test_simple_japanese(self, analyzer: IntentAnalyzer, llm: AsyncMock) -> None:
        subtasks = await analyzer.decompose("FizzBuzzを書いて")

        assert len(subtasks) == 1
        assert subtasks[0].description == "FizzBuzzを書いて"
        llm.complete.assert_not_called()

    async def test_explain_is_simple(self, analyzer: IntentAnalyzer, llm: AsyncMock) -> None:
        subtasks = await analyzer.decompose("Explain how quicksort works")

        assert len(subtasks) == 1
        llm.complete.assert_not_called()

    async def test_tool_requiring_upgrades_to_medium(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        """TD-158: Short tool-requiring goals (weather, search) get MEDIUM decomposition."""
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "Search weather data for Saitama", "deps": []},
                    {"description": "Summarize forecast", "deps": [0]},
                ]
            )
        )
        subtasks = await analyzer.decompose("明日の天気を教えて")

        # Should call LLM (NOT single-subtask wrap) because upgraded to MEDIUM
        llm.complete.assert_called_once()
        assert len(subtasks) == 2
        # Complexity should be MEDIUM (upgraded from SIMPLE)
        from domain.value_objects.task_complexity import TaskComplexity

        assert all(st.complexity == TaskComplexity.MEDIUM for st in subtasks)


class TestComplexityAwarePrompt:
    """Sprint 9.1: MEDIUM/COMPLEX goals use complexity-aware LLM prompt."""

    async def test_medium_goal_calls_llm(self, analyzer: IntentAnalyzer, llm: AsyncMock) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "Create API endpoint", "deps": []},
                    {"description": "Write tests", "deps": [0]},
                ]
            )
        )
        subtasks = await analyzer.decompose("Create a REST API endpoint with unit tests")

        assert len(subtasks) == 2
        llm.complete.assert_called_once()

    async def test_medium_prompt_contains_guidance(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps([{"description": "Step 1", "deps": []}])
        )
        await analyzer.decompose("Create a REST API endpoint with database integration")

        call_args = llm.complete.call_args[0][0]
        system_msg = call_args[0]["content"]
        assert "2-3 subtasks" in system_msg

    async def test_complex_prompt_contains_guidance(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps([{"description": "Step 1", "deps": []}])
        )
        await analyzer.decompose("Build REST API with authentication, database, and testing")

        call_args = llm.complete.call_args[0][0]
        system_msg = call_args[0]["content"]
        assert "3-5 subtasks" in system_msg

    async def test_prompt_requires_action_oriented(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps([{"description": "Step 1", "deps": []}])
        )
        await analyzer.decompose("Create a REST API with database integration")

        call_args = llm.complete.call_args[0][0]
        system_msg = call_args[0]["content"]
        assert "action-oriented" in system_msg


class TestMultiModelDecomposition:
    """Sprint 12.5→12.6: Multi-model goals → LLM-differentiated subtasks."""

    async def test_three_models_produce_subtasks_with_llm(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "Search showtimes", "model": _GEMINI, "deps": []},
                    {"description": "Find coupons", "model": _GPT, "deps": []},
                    {"description": "Recommend best", "model": _CLAUDE, "deps": [0, 1]},
                ]
            )
        )
        subtasks = await analyzer.decompose(
            "gptとgemini,claudeと一緒に映画チケットを探して",
        )

        assert len(subtasks) == 3
        models = {st.preferred_model for st in subtasks}
        assert _GPT in models
        assert _GEMINI in models
        assert _CLAUDE in models

    async def test_multi_model_calls_llm(self, analyzer: IntentAnalyzer, llm: AsyncMock) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "Task A", "model": _GPT, "deps": []},
                    {"description": "Task B", "model": _CLAUDE, "deps": []},
                ]
            )
        )
        await analyzer.decompose("GPT and Claude compare results")
        llm.complete.assert_called_once()

    async def test_multi_model_differentiated_descriptions(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "Search frameworks", "model": _GPT, "deps": []},
                    {"description": "Evaluate perf", "model": _GEMINI, "deps": []},
                ]
            )
        )
        subtasks = await analyzer.decompose("GPT and Gemini test this")
        descriptions = [st.description for st in subtasks]
        assert descriptions[0] != descriptions[1]

    async def test_multi_model_complexity_at_least_medium(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        from domain.value_objects.task_complexity import TaskComplexity

        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "FizzBuzz GPT", "model": _GPT, "deps": []},
                    {"description": "FizzBuzz Claude", "model": _CLAUDE, "deps": []},
                ]
            )
        )
        subtasks = await analyzer.decompose("GPT and Claude do FizzBuzz")
        for st in subtasks:
            assert st.complexity is not None
            assert st.complexity.value >= TaskComplexity.MEDIUM.value

    async def test_multi_model_deps_resolved(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "Research showtimes", "model": _GEMINI, "deps": []},
                    {"description": "Find coupons", "model": _GPT, "deps": []},
                    {"description": "Synthesize", "model": _CLAUDE, "deps": [0, 1]},
                ]
            )
        )
        subtasks = await analyzer.decompose(
            "gptとgemini,claudeと一緒に映画チケットを探して",
        )
        assert subtasks[2].dependencies == [subtasks[0].id, subtasks[1].id]
        assert subtasks[0].dependencies == []

    async def test_multi_model_invalid_model_round_robin(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        """Unknown model in LLM response → round-robin."""
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "Task A", "model": "unknown", "deps": []},
                    {"description": "Task B", "model": "also-x", "deps": []},
                ]
            )
        )
        subtasks = await analyzer.decompose("GPT and Claude solve this")
        assert subtasks[0].preferred_model == _GPT
        assert subtasks[1].preferred_model == _CLAUDE

    async def test_multi_model_llm_failure_fallback(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        """LLM failure falls back to static per-model subtasks."""
        llm.complete.side_effect = RuntimeError("LLM unavailable")
        subtasks = await analyzer.decompose(
            "GPT and Claude do this task",
        )

        assert len(subtasks) == 2
        models = {st.preferred_model for st in subtasks}
        assert _GPT in models
        assert _CLAUDE in models
        for st in subtasks:
            assert st.preferred_model in st.description

    async def test_multi_model_prompt_contains_capabilities(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "Task A", "model": _GPT, "deps": []},
                    {"description": "Task B", "model": _CLAUDE, "deps": []},
                ]
            )
        )
        await analyzer.decompose("GPT and Claude analyze data")
        call_args = llm.complete.call_args[0][0]
        system_msg = call_args[0]["content"]
        assert _GPT in system_msg
        assert _CLAUDE in system_msg
        assert "collaboration mode" in system_msg.lower()


class TestSingleModelPreference:
    """Sprint 12.5: Single model preference stamped on all subtasks."""

    async def test_single_model_stamps_preferred(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "Search flights", "deps": []},
                    {"description": "Compare prices", "deps": [0]},
                ]
            )
        )
        subtasks = await analyzer.decompose("Claude to build REST API with database integration")

        for st in subtasks:
            assert st.preferred_model == "claude-sonnet-4-6"

    async def test_no_model_no_preferred(self, analyzer: IntentAnalyzer, llm: AsyncMock) -> None:
        subtasks = await analyzer.decompose("FizzBuzz")
        assert subtasks[0].preferred_model is None


class TestRoleAssignment:
    """Sprint 13.3: Discussion role assignment in multi-model decomposition."""

    async def test_user_specified_roles_assigned(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        """User-specified roles (via 'role:') take priority."""
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "Argue for", "model": _CLAUDE, "deps": []},
                    {"description": "Argue against", "model": _GPT, "deps": []},
                ]
            )
        )
        subtasks = await analyzer.decompose("claudeとgptで議論して、role: 賛成派, 反対派")

        assert subtasks[0].role == "賛成派"
        assert subtasks[1].role == "反対派"

    async def test_llm_generated_roles_parsed(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        """LLM-generated roles from JSON 'role' field are preserved."""
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {
                        "description": "Analyze data",
                        "model": _CLAUDE,
                        "role": "data scientist",
                        "deps": [],
                    },
                    {
                        "description": "Review code",
                        "model": _GPT,
                        "role": "code reviewer",
                        "deps": [],
                    },
                ]
            )
        )
        subtasks = await analyzer.decompose("claude and gpt analyze this codebase")

        assert subtasks[0].role == "data scientist"
        assert subtasks[1].role == "code reviewer"

    async def test_user_roles_override_llm_roles(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        """User-specified roles override LLM-generated roles."""
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {
                        "description": "Task A",
                        "model": _CLAUDE,
                        "role": "llm_role_A",
                        "deps": [],
                    },
                    {
                        "description": "Task B",
                        "model": _GPT,
                        "role": "llm_role_B",
                        "deps": [],
                    },
                ]
            )
        )
        subtasks = await analyzer.decompose(
            "claude and gpt analyze, role: user_role_X, user_role_Y"
        )

        # User roles take priority
        assert subtasks[0].role == "user_role_X"
        assert subtasks[1].role == "user_role_Y"

    async def test_no_roles_when_disabled(self, llm: AsyncMock) -> None:
        """When role_assignment=False, no roles generated by LLM."""
        analyzer = IntentAnalyzer(llm, role_assignment=False)
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "Task A", "model": _CLAUDE, "deps": []},
                    {"description": "Task B", "model": _GPT, "deps": []},
                ]
            )
        )
        subtasks = await analyzer.decompose("claude and gpt analyze data")

        for st in subtasks:
            assert st.role is None

    async def test_role_assignment_prompt_includes_role_field(
        self, analyzer: IntentAnalyzer, llm: AsyncMock
    ) -> None:
        """When role_assignment enabled, LLM prompt includes role field."""
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "Task A", "model": _CLAUDE, "deps": []},
                    {"description": "Task B", "model": _GPT, "deps": []},
                ]
            )
        )
        await analyzer.decompose("claude and gpt analyze market trends")

        call_args = llm.complete.call_args[0][0]
        system_msg = call_args[0]["content"]
        assert "role" in system_msg.lower()

    async def test_roles_wrap_around(self, analyzer: IntentAnalyzer, llm: AsyncMock) -> None:
        """When fewer roles than subtasks, roles wrap around."""
        llm.complete.return_value = _llm_response(
            json.dumps(
                [
                    {"description": "Task A", "model": _CLAUDE, "deps": []},
                    {"description": "Task B", "model": _GPT, "deps": []},
                    {"description": "Task C", "model": _GEMINI, "deps": []},
                ]
            )
        )
        subtasks = await analyzer.decompose("claude, gpt, geminiで分析して、role: alpha, beta")

        assert subtasks[0].role == "alpha"
        assert subtasks[1].role == "beta"
        assert subtasks[2].role == "alpha"  # wraps around

    async def test_single_model_no_roles(self, analyzer: IntentAnalyzer, llm: AsyncMock) -> None:
        """Single model tasks don't get roles assigned."""
        subtasks = await analyzer.decompose("FizzBuzzを書いて")

        assert subtasks[0].role is None


class TestExtractJson:
    """JSON extraction from various LLM output formats."""

    def test_plain_json(self) -> None:
        result = IntentAnalyzer._extract_json('[{"description": "x", "deps": []}]')
        assert json.loads(result)[0]["description"] == "x"

    def test_markdown_code_block(self) -> None:
        text = '```json\n[{"description": "x", "deps": []}]\n```'
        result = IntentAnalyzer._extract_json(text)
        assert json.loads(result)[0]["description"] == "x"

    def test_think_tags_stripped(self) -> None:
        text = '<think>reasoning</think>\n[{"description": "x", "deps": []}]'
        result = IntentAnalyzer._extract_json(text)
        assert json.loads(result)[0]["description"] == "x"

    def test_surrounding_text(self) -> None:
        text = 'Here is the plan:\n[{"description": "x", "deps": []}]\nDone.'
        result = IntentAnalyzer._extract_json(text)
        assert json.loads(result)[0]["description"] == "x"
