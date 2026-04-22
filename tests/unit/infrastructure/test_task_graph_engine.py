"""Tests for LangGraphTaskEngine — DAG execution with parallel + retry."""

from unittest.mock import AsyncMock

import pytest

from domain.entities.task import SubTask, TaskEntity
from domain.ports.llm_gateway import LLMGateway, LLMResponse
from domain.value_objects.status import SubTaskStatus
from infrastructure.task_graph.engine import LangGraphTaskEngine
from infrastructure.task_graph.intent_analyzer import IntentAnalyzer


def _ok_response(content: str = "result", cost: float = 0.0) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="ollama/qwen3:8b",
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=cost,
    )


@pytest.fixture
def llm() -> AsyncMock:
    return AsyncMock(spec=LLMGateway)


@pytest.fixture
def analyzer() -> AsyncMock:
    return AsyncMock(spec=IntentAnalyzer)


@pytest.fixture
def engine(llm: AsyncMock, analyzer: AsyncMock) -> LangGraphTaskEngine:
    return LangGraphTaskEngine(llm, analyzer)


class TestExecute:
    async def test_single_subtask_success(
        self, engine: LangGraphTaskEngine, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _ok_response("fibonacci done")
        task = TaskEntity(
            goal="Implement fibonacci",
            subtasks=[SubTask(description="Write code")],
        )

        result = await engine.execute(task)

        assert result.subtasks[0].status == SubTaskStatus.SUCCESS
        assert result.subtasks[0].result == "fibonacci done"
        assert result.subtasks[0].model_used == "ollama/qwen3:8b"

    async def test_parallel_independent_subtasks(
        self, engine: LangGraphTaskEngine, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _ok_response("done")
        s1 = SubTask(description="Task A")
        s2 = SubTask(description="Task B")
        task = TaskEntity(goal="Parallel test", subtasks=[s1, s2])

        result = await engine.execute(task)

        assert result.subtasks[0].status == SubTaskStatus.SUCCESS
        assert result.subtasks[1].status == SubTaskStatus.SUCCESS
        # Both called in same batch → parallel via asyncio.gather
        assert llm.complete.await_count == 2

    async def test_sequential_dependent_subtasks(
        self, engine: LangGraphTaskEngine, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _ok_response("done")
        s1 = SubTask(description="Build foundation")
        s2 = SubTask(description="Build on top", dependencies=[s1.id])
        task = TaskEntity(goal="Sequential test", subtasks=[s1, s2])

        result = await engine.execute(task)

        assert result.subtasks[0].status == SubTaskStatus.SUCCESS
        assert result.subtasks[1].status == SubTaskStatus.SUCCESS
        # s1 in first batch, s2 in second → 2 LLM calls across 2 iterations
        assert llm.complete.await_count == 2

    async def test_retry_on_failure(self, engine: LangGraphTaskEngine, llm: AsyncMock) -> None:
        llm.complete.side_effect = [
            Exception("Ollama timeout"),
            _ok_response("recovered"),
        ]
        task = TaskEntity(
            goal="Retry test",
            subtasks=[SubTask(description="Flaky task")],
        )

        result = await engine.execute(task)

        assert result.subtasks[0].status == SubTaskStatus.SUCCESS
        assert result.subtasks[0].result == "recovered"
        assert llm.complete.await_count == 2

    async def test_max_retries_marks_failed(
        self, engine: LangGraphTaskEngine, llm: AsyncMock
    ) -> None:
        llm.complete.side_effect = [
            Exception("fail 1"),
            Exception("fail 2"),
        ]
        task = TaskEntity(
            goal="Fail test",
            subtasks=[SubTask(description="Always fails")],
        )

        result = await engine.execute(task)

        assert result.subtasks[0].status == SubTaskStatus.FAILED
        assert "fail 2" in (result.subtasks[0].error or "")
        assert llm.complete.await_count == 2

    async def test_cascading_failure_blocks_dependents(
        self, engine: LangGraphTaskEngine, llm: AsyncMock
    ) -> None:
        llm.complete.side_effect = [
            Exception("fail 1"),
            Exception("fail 2"),
        ]
        s1 = SubTask(description="Foundation")
        s2 = SubTask(description="Dependent", dependencies=[s1.id])
        task = TaskEntity(goal="Cascade test", subtasks=[s1, s2])

        result = await engine.execute(task)

        assert result.subtasks[0].status == SubTaskStatus.FAILED
        assert result.subtasks[1].status == SubTaskStatus.FAILED
        assert "Blocked" in (result.subtasks[1].error or "")

    async def test_empty_task_completes_immediately(
        self, engine: LangGraphTaskEngine, llm: AsyncMock
    ) -> None:
        task = TaskEntity(goal="Empty task", subtasks=[])

        await engine.execute(task)

        llm.complete.assert_not_awaited()

    async def test_accumulates_cost(self, engine: LangGraphTaskEngine, llm: AsyncMock) -> None:
        llm.complete.side_effect = [
            _ok_response("a", cost=0.01),
            _ok_response("b", cost=0.02),
        ]
        s1 = SubTask(description="Task A")
        s2 = SubTask(description="Task B")
        task = TaskEntity(goal="Cost test", subtasks=[s1, s2])

        result = await engine.execute(task)

        assert result.total_cost_usd == pytest.approx(0.03)


class TestPreferredModelPassthrough:
    """Sprint 12.5: preferred_model forwarded to ReAct/LLM calls."""

    async def test_preferred_model_passed_to_llm(
        self, engine: LangGraphTaskEngine, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _ok_response("done")
        st = SubTask(description="Use Claude", preferred_model="claude-sonnet-4-6")
        task = TaskEntity(goal="Test", subtasks=[st])

        await engine.execute(task)

        call_kwargs = llm.complete.call_args[1]
        assert call_kwargs["model"] == "claude-sonnet-4-6"

    async def test_no_preferred_model_passes_none(
        self, engine: LangGraphTaskEngine, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _ok_response("done")
        st = SubTask(description="No model pref")
        task = TaskEntity(goal="Test", subtasks=[st])

        await engine.execute(task)

        call_kwargs = llm.complete.call_args[1]
        assert call_kwargs["model"] is None

    async def test_preferred_model_passed_to_react(
        self, llm: AsyncMock, analyzer: AsyncMock
    ) -> None:
        from domain.entities.react_trace import ReactTrace
        from infrastructure.task_graph.react_executor import ReactResult

        mock_react = AsyncMock()
        mock_react.execute = AsyncMock(
            return_value=ReactResult(
                trace=ReactTrace(),
                final_answer="done",
                total_cost_usd=0.0,
                model_used="claude-sonnet-4-6",
            )
        )
        engine = LangGraphTaskEngine(llm=llm, analyzer=analyzer, react_executor=mock_react)
        st = SubTask(description="Use Claude", preferred_model="claude-sonnet-4-6")
        task = TaskEntity(goal="Test", subtasks=[st])

        await engine.execute(task)

        call_kwargs = mock_react.execute.call_args[1]
        assert call_kwargs["model"] == "claude-sonnet-4-6"


class TestEngineRouting:
    """Sprint 12.2: Subtasks with preferred_model → autonomous agent runtime."""

    @staticmethod
    def _engine_result(
        success: bool = True, output: str = "engine output", cost: float = 0.05
    ) -> object:
        from domain.ports.agent_engine import AgentEngineResult
        from domain.value_objects.agent_engine import AgentEngineType

        return AgentEngineResult(
            engine=AgentEngineType.CLAUDE_CODE,
            success=success,
            output=output,
            cost_usd=cost,
            model_used="claude-sonnet-4-6",
            error=None if success else "engine unavailable",
        )

    async def test_engine_route_used_when_available(
        self, llm: AsyncMock, analyzer: AsyncMock
    ) -> None:
        """When route_to_engine is set and preferred_model maps to an engine,
        the engine driver is used instead of LLM/ReactExecutor."""
        mock_route = AsyncMock()
        mock_route.execute = AsyncMock(return_value=self._engine_result())
        engine = LangGraphTaskEngine(llm=llm, analyzer=analyzer, route_to_engine=mock_route)
        st = SubTask(description="Analyze code", preferred_model="claude-sonnet-4-6")
        task = TaskEntity(goal="Test", subtasks=[st])

        result = await engine.execute(task)

        mock_route.execute.assert_awaited_once()
        assert result.subtasks[0].status == SubTaskStatus.SUCCESS
        assert result.subtasks[0].engine_used == "claude_code"
        assert result.subtasks[0].model_used == "claude-sonnet-4-6"
        assert result.subtasks[0].cost_usd == 0.05
        assert result.subtasks[0].result == "engine output"
        # LLM.complete should NOT be called — engine handled it
        llm.complete.assert_not_awaited()

    async def test_engine_route_fallback_to_react(
        self, llm: AsyncMock, analyzer: AsyncMock
    ) -> None:
        """When engine routing fails, fall back to ReactExecutor."""
        from domain.entities.react_trace import ReactTrace
        from infrastructure.task_graph.react_executor import ReactResult

        mock_route = AsyncMock()
        mock_route.execute = AsyncMock(return_value=self._engine_result(success=False))
        mock_react = AsyncMock()
        mock_react.execute = AsyncMock(
            return_value=ReactResult(
                trace=ReactTrace(),
                final_answer="react fallback",
                total_cost_usd=0.03,
                model_used="claude-sonnet-4-6",
                tools_used=["web_search"],
                data_sources=["https://example.com"],
            )
        )
        engine = LangGraphTaskEngine(
            llm=llm,
            analyzer=analyzer,
            react_executor=mock_react,
            route_to_engine=mock_route,
        )
        st = SubTask(description="Search the web", preferred_model="claude-sonnet-4-6")
        task = TaskEntity(goal="Test", subtasks=[st])

        result = await engine.execute(task)

        # Engine tried and failed
        mock_route.execute.assert_awaited_once()
        # ReactExecutor was used as fallback
        mock_react.execute.assert_awaited_once()
        assert result.subtasks[0].status == SubTaskStatus.SUCCESS
        assert result.subtasks[0].result == "react fallback"

    async def test_engine_route_fallback_to_direct_llm(
        self, llm: AsyncMock, analyzer: AsyncMock
    ) -> None:
        """When engine fails and no ReactExecutor, fall back to direct LLM."""
        mock_route = AsyncMock()
        mock_route.execute = AsyncMock(return_value=self._engine_result(success=False))
        llm.complete.return_value = _ok_response("direct llm fallback")
        engine = LangGraphTaskEngine(llm=llm, analyzer=analyzer, route_to_engine=mock_route)
        st = SubTask(description="Simple task", preferred_model="claude-sonnet-4-6")
        task = TaskEntity(goal="Test", subtasks=[st])

        result = await engine.execute(task)

        mock_route.execute.assert_awaited_once()
        llm.complete.assert_awaited_once()
        assert result.subtasks[0].result == "direct llm fallback"

    async def test_engine_route_not_used_without_preferred_model(
        self, llm: AsyncMock, analyzer: AsyncMock
    ) -> None:
        """No preferred_model → engine_type is None → no engine routing."""
        mock_route = AsyncMock()
        llm.complete.return_value = _ok_response("direct")
        engine = LangGraphTaskEngine(llm=llm, analyzer=analyzer, route_to_engine=mock_route)
        st = SubTask(description="Simple task")
        task = TaskEntity(goal="Test", subtasks=[st])

        await engine.execute(task)

        mock_route.execute.assert_not_awaited()
        llm.complete.assert_awaited_once()

    async def test_engine_route_not_used_for_unknown_model(
        self, llm: AsyncMock, analyzer: AsyncMock
    ) -> None:
        """preferred_model that doesn't map to any engine → no engine routing."""
        mock_route = AsyncMock()
        llm.complete.return_value = _ok_response("done")
        engine = LangGraphTaskEngine(llm=llm, analyzer=analyzer, route_to_engine=mock_route)
        st = SubTask(description="Task", preferred_model="unknown-model-xyz")
        task = TaskEntity(goal="Test", subtasks=[st])

        await engine.execute(task)

        mock_route.execute.assert_not_awaited()

    async def test_engine_route_parallel_multi_model(
        self, llm: AsyncMock, analyzer: AsyncMock
    ) -> None:
        """Multiple subtasks with different engines run in parallel."""
        from domain.ports.agent_engine import AgentEngineResult
        from domain.value_objects.agent_engine import AgentEngineType

        call_count = 0

        async def mock_execute(**kwargs: object) -> AgentEngineResult:
            nonlocal call_count
            call_count += 1
            engine = AgentEngineType.CLAUDE_CODE
            model = "claude-sonnet-4-6"
            if call_count == 2:
                engine = AgentEngineType.GEMINI_CLI
                model = "gemini/gemini-3-pro-preview"
            return AgentEngineResult(
                engine=engine,
                success=True,
                output=f"result from {engine.value}",
                cost_usd=0.02,
                model_used=model,
            )

        mock_route = AsyncMock()
        mock_route.execute = AsyncMock(side_effect=mock_execute)
        # Discussion phase calls llm.complete for synthesis
        llm.complete.return_value = _ok_response("synthesized", cost=0.01)
        engine = LangGraphTaskEngine(llm=llm, analyzer=analyzer, route_to_engine=mock_route)
        s1 = SubTask(description="Part A", preferred_model="claude-sonnet-4-6")
        s2 = SubTask(description="Part B", preferred_model="gemini/gemini-3-pro-preview")
        task = TaskEntity(goal="Multi-engine", subtasks=[s1, s2])

        result = await engine.execute(task)

        assert mock_route.execute.await_count == 2
        assert result.subtasks[0].engine_used == "claude_code"
        assert result.subtasks[1].engine_used == "gemini_cli"
        # 2 engine subtasks ($0.02 each) + discussion phase ($0.01)
        assert result.total_cost_usd == pytest.approx(0.05)


class TestEngineRoutingObservability:
    """Sprint 12.8: Engine routing — data_sources extraction + DEGRADED skip."""

    @staticmethod
    def _engine_result_with_urls(
        output: str = "See https://example.com and https://test.org/page",
    ) -> object:
        from domain.ports.agent_engine import AgentEngineResult
        from domain.value_objects.agent_engine import AgentEngineType

        return AgentEngineResult(
            engine=AgentEngineType.CLAUDE_CODE,
            success=True,
            output=output,
            cost_usd=0.05,
            model_used="claude-sonnet-4-6",
        )

    async def test_engine_output_urls_become_data_sources(
        self, llm: AsyncMock, analyzer: AsyncMock
    ) -> None:
        """URLs in engine output are extracted to subtask.data_sources."""
        mock_route = AsyncMock()
        mock_route.execute = AsyncMock(return_value=self._engine_result_with_urls())
        engine = LangGraphTaskEngine(llm=llm, analyzer=analyzer, route_to_engine=mock_route)
        st = SubTask(description="Search web", preferred_model="claude-sonnet-4-6")
        task = TaskEntity(goal="Test", subtasks=[st])

        result = await engine.execute(task)

        assert result.subtasks[0].data_sources == [
            "https://example.com",
            "https://test.org/page",
        ]

    async def test_engine_output_no_urls_empty_data_sources(
        self, llm: AsyncMock, analyzer: AsyncMock
    ) -> None:
        """Engine output without URLs → data_sources stays empty."""
        from domain.ports.agent_engine import AgentEngineResult
        from domain.value_objects.agent_engine import AgentEngineType

        mock_route = AsyncMock()
        mock_route.execute = AsyncMock(
            return_value=AgentEngineResult(
                engine=AgentEngineType.CLAUDE_CODE,
                success=True,
                output="The answer is 42",
                cost_usd=0.01,
                model_used="claude-sonnet-4-6",
            )
        )
        engine = LangGraphTaskEngine(llm=llm, analyzer=analyzer, route_to_engine=mock_route)
        st = SubTask(description="Simple math", preferred_model="claude-sonnet-4-6")
        task = TaskEntity(goal="Test", subtasks=[st])

        result = await engine.execute(task)

        assert not result.subtasks[0].data_sources

    async def test_engine_routed_subtask_not_marked_degraded(
        self, llm: AsyncMock, analyzer: AsyncMock
    ) -> None:
        """Engine-routed subtask requiring tools but tools_used=[] stays SUCCESS.
        Autonomous runtimes handle tools internally."""
        from domain.ports.agent_engine import AgentEngineResult
        from domain.value_objects.agent_engine import AgentEngineType

        mock_route = AsyncMock()
        mock_route.execute = AsyncMock(
            return_value=AgentEngineResult(
                engine=AgentEngineType.GEMINI_CLI,
                success=True,
                output="Weather in Tokyo is sunny",
                cost_usd=0.02,
                model_used="gemini/gemini-3-pro-preview",
            )
        )
        engine = LangGraphTaskEngine(llm=llm, analyzer=analyzer, route_to_engine=mock_route)
        # "検索して" triggers requires_tools() → would be DEGRADED without engine_used
        st = SubTask(
            description="東京の天気を検索して",
            preferred_model="gemini/gemini-3-pro-preview",
        )
        task = TaskEntity(goal="Test", subtasks=[st])

        result = await engine.execute(task)

        # Must be SUCCESS, NOT DEGRADED — engine handled tools internally
        assert result.subtasks[0].status == SubTaskStatus.SUCCESS
        assert result.subtasks[0].engine_used == "gemini_cli"


class TestSmartAutoUpgrade:
    """Sprint 12.8: _pick_upgrade_model checks API key availability."""

    async def test_picks_first_available_model(self, analyzer: AsyncMock) -> None:
        llm = AsyncMock(spec=LLMGateway)
        # Claude unavailable, GPT unavailable, Gemini available
        llm.is_available = AsyncMock(side_effect=lambda m: m == "gemini/gemini-2.5-flash")
        engine = LangGraphTaskEngine(llm=llm, analyzer=analyzer)

        result = await engine._pick_upgrade_model()

        assert result == "gemini/gemini-2.5-flash"

    async def test_returns_none_when_all_unavailable(self, analyzer: AsyncMock) -> None:
        llm = AsyncMock(spec=LLMGateway)
        llm.is_available = AsyncMock(return_value=False)
        engine = LangGraphTaskEngine(llm=llm, analyzer=analyzer)

        result = await engine._pick_upgrade_model()

        assert result is None

    async def test_picks_claude_first_when_available(self, analyzer: AsyncMock) -> None:
        llm = AsyncMock(spec=LLMGateway)
        llm.is_available = AsyncMock(return_value=True)
        engine = LangGraphTaskEngine(llm=llm, analyzer=analyzer)

        result = await engine._pick_upgrade_model()

        assert result == "claude-sonnet-4-6"  # first in _AUTO_UPGRADE_MODELS


class TestExtractUrls:
    """Sprint 12.8: URL extraction utility."""

    def test_extracts_multiple_urls(self) -> None:
        from infrastructure.task_graph.engine import _extract_urls

        text = "Visit https://a.com and https://b.org/page?q=1 for details"
        assert _extract_urls(text) == ["https://a.com", "https://b.org/page?q=1"]

    def test_deduplicates_urls(self) -> None:
        from infrastructure.task_graph.engine import _extract_urls

        text = "https://a.com is great. Again https://a.com"
        assert _extract_urls(text) == ["https://a.com"]

    def test_no_urls_returns_empty(self) -> None:
        from infrastructure.task_graph.engine import _extract_urls

        assert _extract_urls("The answer is 42") == []

    def test_handles_http_and_https(self) -> None:
        from infrastructure.task_graph.engine import _extract_urls

        text = "http://old.com and https://new.com"
        assert _extract_urls(text) == ["http://old.com", "https://new.com"]


class TestAutoRoute:
    """TD-155: Auto-route selects engine when preferred_model is None."""

    async def test_auto_route_code_gen_to_codex(
        self, llm: AsyncMock, analyzer: AsyncMock
    ) -> None:
        """Backend subtask auto-routes to codex_cli via RouteToEngineUseCase."""

        from domain.ports.agent_engine import AgentEngineResult
        from domain.value_objects.agent_engine import AgentEngineType

        mock_route = AsyncMock()
        mock_route.execute = AsyncMock(
            return_value=AgentEngineResult(
                engine=AgentEngineType.CODEX_CLI,
                success=True,
                output="Codex generated the API",
                cost_usd=0.01,
                model_used="gpt-4o",
            ),
        )
        engine = LangGraphTaskEngine(
            llm, analyzer, route_to_engine=mock_route, task_budget=1.0,
        )

        task = TaskEntity(
            goal="Build REST API",
            subtasks=[SubTask(description="Implement FastAPI REST endpoints")],
        )
        result = await engine.execute(task)

        assert result.subtasks[0].status == SubTaskStatus.SUCCESS
        assert result.subtasks[0].engine_used == "codex_cli"
        assert result.subtasks[0].model_used == "gpt-4o"
        mock_route.execute.assert_awaited_once()

    async def test_auto_route_simple_qa_stays_local(
        self, llm: AsyncMock, analyzer: AsyncMock
    ) -> None:
        """Simple general task stays on local LLM (Ollama), no engine route."""

        mock_route = AsyncMock()
        llm.complete.return_value = _ok_response("42")
        engine = LangGraphTaskEngine(
            llm, analyzer, route_to_engine=mock_route, task_budget=1.0,
        )

        task = TaskEntity(
            goal="Simple math",
            subtasks=[SubTask(description="Calculate 6*7")],
        )
        result = await engine.execute(task)

        assert result.subtasks[0].status == SubTaskStatus.SUCCESS
        # Should NOT call engine routing (SIMPLE_QA → OLLAMA → skip)
        mock_route.execute.assert_not_awaited()

    async def test_auto_route_zero_budget_stays_ollama(
        self, llm: AsyncMock, analyzer: AsyncMock
    ) -> None:
        """budget=0 → AgentEngineRouter returns OLLAMA → skip engine route."""
        mock_route = AsyncMock()
        llm.complete.return_value = _ok_response("done")
        engine = LangGraphTaskEngine(
            llm, analyzer, route_to_engine=mock_route, task_budget=0.0,
        )

        task = TaskEntity(
            goal="Build API",
            subtasks=[SubTask(description="Implement FastAPI endpoints")],
        )
        result = await engine.execute(task)

        assert result.subtasks[0].status == SubTaskStatus.SUCCESS
        mock_route.execute.assert_not_awaited()

    async def test_auto_route_fallback_on_engine_failure(
        self, llm: AsyncMock, analyzer: AsyncMock
    ) -> None:
        """When engine route fails, falls back to direct LLM."""
        from domain.ports.agent_engine import AgentEngineResult
        from domain.value_objects.agent_engine import AgentEngineType

        mock_route = AsyncMock()
        mock_route.execute = AsyncMock(
            return_value=AgentEngineResult(
                engine=AgentEngineType.CODEX_CLI,
                success=False,
                output="",
                cost_usd=0.0,
                error="Codex CLI unavailable",
            ),
        )
        llm.complete.return_value = _ok_response("fallback result")
        engine = LangGraphTaskEngine(
            llm, analyzer, route_to_engine=mock_route, task_budget=1.0,
        )

        task = TaskEntity(
            goal="Build API",
            subtasks=[SubTask(description="Implement FastAPI REST endpoints")],
        )
        result = await engine.execute(task)

        assert result.subtasks[0].status == SubTaskStatus.SUCCESS
        assert result.subtasks[0].result == "fallback result"
        # Engine was tried but failed, fell back to direct LLM
        mock_route.execute.assert_awaited_once()
        llm.complete.assert_awaited_once()

    async def test_explicit_model_bypasses_auto_route(
        self, llm: AsyncMock, analyzer: AsyncMock
    ) -> None:
        """When preferred_model is set, use explicit path (not auto-route)."""
        from domain.ports.agent_engine import AgentEngineResult
        from domain.value_objects.agent_engine import AgentEngineType

        mock_route = AsyncMock()
        mock_route.execute = AsyncMock(
            return_value=AgentEngineResult(
                engine=AgentEngineType.CLAUDE_CODE,
                success=True,
                output="Claude did it",
                cost_usd=0.05,
                model_used="claude-sonnet-4-6",
            ),
        )
        engine = LangGraphTaskEngine(
            llm, analyzer, route_to_engine=mock_route, task_budget=1.0,
        )

        task = TaskEntity(
            goal="Build API",
            subtasks=[
                SubTask(
                    description="Implement endpoints",
                    preferred_model="claude-sonnet-4-6",
                ),
            ],
        )
        result = await engine.execute(task)

        assert result.subtasks[0].engine_used == "claude_code"
        # Explicit model path uses _resolve_engine_type, not SubtaskTypeClassifier
        call_kwargs = mock_route.execute.call_args
        assert call_kwargs.kwargs.get("preferred_engine") == AgentEngineType.CLAUDE_CODE


    async def test_auto_route_rejects_ollama_for_tool_requiring_task(
        self, llm: AsyncMock, analyzer: AsyncMock
    ) -> None:
        """TD-156: When auto-route intended CLAUDE_CODE but fell back to OLLAMA
        for a tool-requiring task (e.g. weather), reject OLLAMA result and use
        ReactExecutor auto-upgrade path instead."""
        from domain.ports.agent_engine import AgentEngineResult
        from domain.value_objects.agent_engine import AgentEngineType

        mock_route = AsyncMock()
        # Simulate: intended CLAUDE_CODE but all engines fell to OLLAMA
        mock_route.execute = AsyncMock(
            return_value=AgentEngineResult(
                engine=AgentEngineType.OLLAMA,  # fell back to OLLAMA
                success=True,
                output="天気情報にアクセスできません",
                cost_usd=0.0,
                engines_tried=["claude_code", "codex_cli", "gemini_cli", "ollama"],
            ),
        )
        llm.complete.return_value = _ok_response("明日は晴れです (auto-upgrade)")
        engine = LangGraphTaskEngine(
            llm, analyzer, route_to_engine=mock_route, task_budget=1.0,
        )

        task = TaskEntity(
            goal="明日の天気を教えて",
            # 天気 triggers requires_tools → WEB_SEARCH → GEMINI_CLI
            subtasks=[SubTask(description="明日の埼玉の天気を教えて")],
        )
        result = await engine.execute(task)

        # Engine route was attempted (auto-route fires for weather task)
        mock_route.execute.assert_awaited_once()
        # OLLAMA engine result was rejected — fell through to direct LLM path.
        # Without ReactExecutor, direct LLM can't use tools → DEGRADED.
        # In production with ReactExecutor, auto-upgrade would retry with cloud model.
        st = result.subtasks[0]
        assert st.status == SubTaskStatus.DEGRADED
        # Direct LLM produced an answer but degraded because no tools were used
        assert st.result is not None


class TestDecompose:
    async def test_delegates_to_analyzer(
        self, engine: LangGraphTaskEngine, analyzer: AsyncMock
    ) -> None:
        expected = [SubTask(description="Step 1")]
        analyzer.decompose.return_value = expected

        result = await engine.decompose("Test goal")

        assert result == expected
        analyzer.decompose.assert_awaited_once_with("Test goal")
