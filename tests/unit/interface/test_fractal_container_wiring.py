"""Tests for fractal engine container wiring in AppContainer.

Sprint 15.6 (TD-104): Verify that _create_task_engine() correctly selects
and configures the task engine based on execution_engine setting.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from interface.api.container import AppContainer


class _FakeSettings:
    """Minimal settings for wiring tests — matches test_mcp_server pattern."""

    ollama_base_url = "http://localhost:11434"
    ollama_default_model = "qwen3:8b"
    ollama_coding_model = "qwen3-coder:30b"
    local_first = True
    default_monthly_budget_usd = 50.0
    default_task_budget_usd = 1.0
    auto_downgrade_on_budget = True
    cache_breakpoints_enabled = True
    use_postgres = False
    use_sqlite = False
    database_url = ""
    embedding_backend = "none"
    embedding_model = "all-minilm"
    embedding_dimensions = 384
    is_development = False
    memory_retention_threshold = 0.3
    celery_enabled = False
    openhands_base_url = "http://localhost:3000"
    openhands_model = "claude-sonnet-4-6"
    openhands_api_key = ""
    claude_code_sdk_enabled = False
    claude_code_cli_path = "claude"
    gemini_cli_enabled = False
    gemini_cli_path = "gemini"
    google_gemini_api_key = ""
    codex_cli_enabled = False
    codex_cli_path = "codex"
    adk_enabled = False
    adk_default_model = "gemini-2.5-flash"
    context_bridge_default_tokens = 800
    mcp_enabled = False
    mcp_transport = "stdio"
    mcp_port = 8100
    mcp_servers = "[]"
    marketplace_enabled = False
    marketplace_auto_install = False
    marketplace_safety_threshold = "experimental"
    mcp_registry_url = "https://registry.modelcontextprotocol.io"
    affinity_min_samples = 3
    affinity_boost_threshold = 0.6
    evolution_enabled = False
    evolution_strategy_dir = Path("/tmp/morphic_test_evolution")
    evolution_auto_update = False
    evolution_min_samples = 10
    semantic_dedup_enabled = False
    semantic_dedup_threshold = 0.85
    token_dedup_threshold = 0.6
    react_enabled = False
    react_max_iterations = 10
    laee_approval_mode = "confirm-destructive"
    laee_audit_log_path = Path("/tmp/morphic_test_audit.jsonl")
    laee_undo_enabled = False
    discussion_max_rounds = 1
    discussion_rotate_models = True
    discussion_role_assignment = True
    discussion_adaptive = False
    discussion_convergence_threshold = 0.85
    discussion_min_rounds = 1
    # Fractal defaults — langgraph mode
    execution_engine = "langgraph"
    fractal_max_depth = 3
    fractal_candidates_per_node = 3
    fractal_plan_eval_models = ""
    fractal_plan_eval_min_score = 0.5
    fractal_result_eval_ok_threshold = 0.7
    fractal_result_eval_retry_threshold = 0.4
    fractal_max_retries = 3
    fractal_max_plan_attempts = 2
    fractal_max_reflection_rounds = 2
    fractal_max_total_nodes = 20
    fractal_max_concurrent_nodes = 3
    fractal_throttle_delay_ms = 0
    fractal_max_execution_seconds = 180
    anthropic_api_key = ""
    openai_api_key = ""

    @property
    def marketplace_safety_threshold_tier(self):  # type: ignore[no-untyped-def]
        from domain.value_objects.tool_safety import SafetyTier

        return SafetyTier.EXPERIMENTAL

    @property
    def has_anthropic(self) -> bool:
        return False

    @property
    def has_openai(self) -> bool:
        return False

    @property
    def has_gemini(self) -> bool:
        return False


def _make_langgraph_settings() -> _FakeSettings:
    s = _FakeSettings()
    s.execution_engine = "langgraph"
    return s


def _make_fractal_settings(**overrides: object) -> _FakeSettings:
    s = _FakeSettings()
    s.execution_engine = "fractal"
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


# ── Default engine selection ──


class TestDefaultEngineSelection:
    def test_langgraph_is_default(self) -> None:
        from infrastructure.task_graph.engine import LangGraphTaskEngine

        container = AppContainer(settings=_make_langgraph_settings())
        assert isinstance(container.task_engine, LangGraphTaskEngine)

    def test_explicit_langgraph_returns_langgraph(self) -> None:
        from infrastructure.task_graph.engine import LangGraphTaskEngine

        s = _FakeSettings()
        s.execution_engine = "langgraph"
        container = AppContainer(settings=s)
        assert isinstance(container.task_engine, LangGraphTaskEngine)

    def test_unknown_engine_falls_back_to_langgraph(self) -> None:
        from infrastructure.task_graph.engine import LangGraphTaskEngine

        s = _FakeSettings()
        s.execution_engine = "nonexistent"
        container = AppContainer(settings=s)
        assert isinstance(container.task_engine, LangGraphTaskEngine)


# ── Fractal engine selection ──


class TestFractalEngineSelection:
    def test_fractal_returns_fractal_engine(self) -> None:
        from infrastructure.fractal.fractal_engine import FractalTaskEngine

        container = AppContainer(settings=_make_fractal_settings())
        assert isinstance(container.task_engine, FractalTaskEngine)

    def test_fractal_wraps_langgraph_engine(self) -> None:
        from infrastructure.fractal.fractal_engine import FractalTaskEngine
        from infrastructure.task_graph.engine import LangGraphTaskEngine

        container = AppContainer(settings=_make_fractal_settings())
        engine = container.task_engine
        assert isinstance(engine, FractalTaskEngine)
        assert isinstance(engine._inner, LangGraphTaskEngine)
        assert engine._inner is container._langgraph_engine

    def test_fractal_has_planner_injected(self) -> None:
        from infrastructure.fractal.llm_planner import LLMPlanner

        container = AppContainer(settings=_make_fractal_settings())
        assert isinstance(container.task_engine._planner, LLMPlanner)

    def test_fractal_has_plan_evaluator_injected(self) -> None:
        from infrastructure.fractal.llm_plan_evaluator import LLMPlanEvaluator

        container = AppContainer(settings=_make_fractal_settings())
        assert isinstance(container.task_engine._plan_evaluator, LLMPlanEvaluator)

    def test_fractal_has_result_evaluator_injected(self) -> None:
        from infrastructure.fractal.llm_result_evaluator import LLMResultEvaluator

        container = AppContainer(settings=_make_fractal_settings())
        assert isinstance(container.task_engine._result_evaluator, LLMResultEvaluator)


# ── Config propagation ──


class TestFractalConfigPropagation:
    def test_max_depth_propagated(self) -> None:
        container = AppContainer(settings=_make_fractal_settings(fractal_max_depth=5))
        assert container.task_engine._max_depth == 5

    def test_max_retries_propagated(self) -> None:
        container = AppContainer(settings=_make_fractal_settings(fractal_max_retries=7))
        assert container.task_engine._max_retries == 7

    def test_max_plan_attempts_propagated(self) -> None:
        container = AppContainer(settings=_make_fractal_settings(fractal_max_plan_attempts=4))
        assert container.task_engine._max_plan_attempts == 4

    def test_plan_eval_min_score_propagated(self) -> None:
        container = AppContainer(settings=_make_fractal_settings(fractal_plan_eval_min_score=0.8))
        assert container.task_engine._plan_eval_min_score == pytest.approx(0.8)

    def test_result_eval_ok_threshold_propagated(self) -> None:
        container = AppContainer(
            settings=_make_fractal_settings(fractal_result_eval_ok_threshold=0.9)
        )
        assert container.task_engine._result_eval_ok_threshold == pytest.approx(0.9)

    def test_result_eval_retry_threshold_propagated(self) -> None:
        container = AppContainer(
            settings=_make_fractal_settings(fractal_result_eval_retry_threshold=0.3)
        )
        assert container.task_engine._result_eval_retry_threshold == pytest.approx(0.3)

    def test_budget_from_settings(self) -> None:
        container = AppContainer(settings=_make_fractal_settings(default_task_budget_usd=2.5))
        assert container.task_engine._budget_usd == pytest.approx(2.5)

    def test_plan_eval_models_parsed(self) -> None:
        container = AppContainer(
            settings=_make_fractal_settings(
                fractal_plan_eval_models="ollama/qwen3:8b, claude-sonnet-4-6"
            )
        )
        evaluator = container.task_engine._plan_evaluator
        assert evaluator._models == ["ollama/qwen3:8b", "claude-sonnet-4-6"]

    def test_plan_eval_models_empty_is_none(self) -> None:
        container = AppContainer(settings=_make_fractal_settings(fractal_plan_eval_models=""))
        evaluator = container.task_engine._plan_evaluator
        # When None is passed, __init__ defaults to []
        assert evaluator._models == [] or evaluator._models is None


# ── Engine routing wiring ──


# ── Learning repo wiring ──


class TestLearningRepoWiring:
    def test_fractal_has_learning_repo_injected(self) -> None:
        from infrastructure.fractal.in_memory_learning_repo import (
            InMemoryFractalLearningRepository,
        )

        container = AppContainer(settings=_make_fractal_settings())
        assert isinstance(container.task_engine._learning_repo, InMemoryFractalLearningRepository)

    def test_fractal_planner_has_learning_repo_injected(self) -> None:
        from domain.ports.fractal_learning_repository import FractalLearningRepository

        container = AppContainer(settings=_make_fractal_settings())
        planner = container.task_engine._planner
        assert isinstance(planner._learning_repo, FractalLearningRepository)

    def test_fractal_with_postgres_uses_pg_repo(self) -> None:
        from infrastructure.persistence.pg_fractal_learning_repository import (
            PgFractalLearningRepository,
        )

        container = AppContainer(
            settings=_make_fractal_settings(
                use_postgres=True,
                database_url="postgresql+asyncpg://test:test@localhost:5432/test",
            )
        )
        assert isinstance(container.task_engine._learning_repo, PgFractalLearningRepository)

    def test_langgraph_mode_no_learning_repo(self) -> None:
        """LangGraphTaskEngine has no _learning_repo attribute."""
        container = AppContainer(settings=_make_langgraph_settings())
        assert not hasattr(container.task_engine, "_learning_repo")


# ── Engine routing wiring ──


class TestEngineRoutingWiring:
    def test_langgraph_has_route_to_engine(self) -> None:
        container = AppContainer(settings=_make_langgraph_settings())
        assert container._langgraph_engine._route_to_engine is container.route_to_engine

    def test_fractal_inner_engine_has_route_to_engine(self) -> None:
        container = AppContainer(settings=_make_fractal_settings())
        inner = container.task_engine._inner
        assert inner._route_to_engine is container.route_to_engine
