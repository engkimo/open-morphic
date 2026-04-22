"""Evolution Pipeline integration tests — Sprint 20.1 (TD-121).

Tests the full Level 1→2→3 self-evolution pipeline with real
InMemory repositories (no mocks), verifying that execution records
flow through analysis, strategy update, and systemic evolution.

Run:
    uv run pytest tests/integration/test_evolution_pipeline.py -v -s
"""

from __future__ import annotations

from pathlib import Path

import pytest

from application.use_cases.analyze_execution import AnalyzeExecutionUseCase
from application.use_cases.systemic_evolution import SystemicEvolutionUseCase
from application.use_cases.update_strategy import UpdateStrategyUseCase
from domain.entities.execution_record import ExecutionRecord
from domain.entities.strategy import RecoveryRule
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.evolution import EvolutionLevel
from domain.value_objects.model_tier import TaskType
from infrastructure.evolution.strategy_store import StrategyStore
from infrastructure.persistence.in_memory_execution_record import (
    InMemoryExecutionRecordRepository,
)

pytestmark = pytest.mark.asyncio

CLAUDE = AgentEngineType.CLAUDE_CODE
GEMINI = AgentEngineType.GEMINI_CLI
OLLAMA = AgentEngineType.OLLAMA


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def exec_repo() -> InMemoryExecutionRecordRepository:
    return InMemoryExecutionRecordRepository()


@pytest.fixture
def strategy_store(tmp_path: Path) -> StrategyStore:
    return StrategyStore(base_dir=tmp_path / "evolution")


@pytest.fixture
def analyze(exec_repo: InMemoryExecutionRecordRepository) -> AnalyzeExecutionUseCase:
    return AnalyzeExecutionUseCase(repo=exec_repo)


@pytest.fixture
def update_strategy(
    exec_repo: InMemoryExecutionRecordRepository,
    strategy_store: StrategyStore,
) -> UpdateStrategyUseCase:
    return UpdateStrategyUseCase(
        execution_repo=exec_repo,
        strategy_store=strategy_store,
        min_samples=3,  # lower threshold for testing
    )


@pytest.fixture
def systemic(
    analyze: AnalyzeExecutionUseCase,
    update_strategy: UpdateStrategyUseCase,
) -> SystemicEvolutionUseCase:
    return SystemicEvolutionUseCase(
        analyze_execution=analyze,
        update_strategy=update_strategy,
        discover_tools=None,  # no registry in integration test
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _record(
    task_type: TaskType = TaskType.CODE_GENERATION,
    engine: AgentEngineType = CLAUDE,
    model: str = "claude-sonnet-4-6",
    success: bool = True,
    cost: float = 0.01,
    duration: float = 5.0,
    error: str | None = None,
    goal: str = "test goal",
) -> ExecutionRecord:
    return ExecutionRecord(
        task_id="task-1",
        task_type=task_type,
        goal=goal,
        engine_used=engine,
        model_used=model,
        success=success,
        error_message=error,
        cost_usd=cost,
        duration_seconds=duration,
    )


async def _seed_records(
    repo: InMemoryExecutionRecordRepository,
    records: list[ExecutionRecord],
) -> None:
    for r in records:
        await repo.save(r)


# ===========================================================================
# Test 1: Execution record lifecycle
# ===========================================================================


async def test_execution_record_save_and_list(
    exec_repo: InMemoryExecutionRecordRepository,
) -> None:
    """Records can be saved, retrieved, and filtered."""
    records = [
        _record(success=True, cost=0.01),
        _record(success=False, cost=0.02, error="timeout"),
        _record(task_type=TaskType.SIMPLE_QA, engine=OLLAMA, model="qwen3:8b"),
    ]
    await _seed_records(exec_repo, records)

    all_records = await exec_repo.list_recent(limit=10)
    assert len(all_records) == 3

    failures = await exec_repo.list_failures()
    assert len(failures) == 1
    assert failures[0].error_message == "timeout"

    by_type = await exec_repo.list_by_task_type(TaskType.SIMPLE_QA)
    assert len(by_type) == 1
    assert by_type[0].engine_used == OLLAMA


# ===========================================================================
# Test 2: Execution stats aggregation
# ===========================================================================


async def test_execution_stats(
    exec_repo: InMemoryExecutionRecordRepository,
    analyze: AnalyzeExecutionUseCase,
) -> None:
    """Stats aggregate correctly across records."""
    records = [
        _record(success=True, cost=0.01, duration=2.0, model="claude-sonnet-4-6"),
        _record(success=True, cost=0.03, duration=4.0, model="claude-sonnet-4-6"),
        _record(success=False, cost=0.00, duration=1.0, model="qwen3:8b", engine=OLLAMA),
    ]
    await _seed_records(exec_repo, records)

    stats = await analyze.get_stats()
    assert stats.total_count == 3
    assert stats.success_count == 2
    assert stats.failure_count == 1
    assert stats.success_rate == pytest.approx(2 / 3, abs=0.01)
    assert stats.avg_cost_usd == pytest.approx(0.04 / 3, abs=0.001)
    assert "claude-sonnet-4-6" in stats.model_distribution
    assert stats.model_distribution["claude-sonnet-4-6"] == 2


# ===========================================================================
# Test 3: Failure pattern analysis
# ===========================================================================


async def test_failure_patterns(
    exec_repo: InMemoryExecutionRecordRepository,
    analyze: AnalyzeExecutionUseCase,
) -> None:
    """Recurring failures are grouped and counted."""
    records = [
        _record(success=False, error="Connection refused: model server down"),
        _record(success=False, error="Connection refused: model server down"),
        _record(success=False, error="Connection refused: model server down"),
        _record(success=False, error="Token limit exceeded"),
        _record(success=True),  # no error
    ]
    await _seed_records(exec_repo, records)

    patterns = await analyze.get_failure_patterns()
    assert len(patterns) >= 2
    assert patterns[0].count == 3  # most common first
    assert "Connection refused" in patterns[0].error_pattern


# ===========================================================================
# Test 4: Model preference update
# ===========================================================================


async def test_model_preference_update(
    exec_repo: InMemoryExecutionRecordRepository,
    update_strategy: UpdateStrategyUseCase,
    strategy_store: StrategyStore,
) -> None:
    """Model preferences are computed and persisted."""
    # 5 Claude records (above min_samples=3)
    records = [
        _record(model="claude-sonnet-4-6", success=True, cost=0.02, duration=3.0) for _ in range(4)
    ] + [
        _record(model="claude-sonnet-4-6", success=False, cost=0.01, duration=1.0),
    ]
    await _seed_records(exec_repo, records)

    prefs = await update_strategy.update_model_preferences()
    assert len(prefs) >= 1

    claude_pref = next(p for p in prefs if p.model == "claude-sonnet-4-6")
    assert claude_pref.success_rate == pytest.approx(0.8, abs=0.01)
    assert claude_pref.sample_count == 5

    # Verify persistence
    loaded = strategy_store.load_model_preferences()
    assert len(loaded) >= 1
    assert loaded[0].model == "claude-sonnet-4-6"


# ===========================================================================
# Test 5: Engine preference update
# ===========================================================================


async def test_engine_preference_update(
    exec_repo: InMemoryExecutionRecordRepository,
    update_strategy: UpdateStrategyUseCase,
    strategy_store: StrategyStore,
) -> None:
    """Engine preferences are computed and persisted."""
    records = [_record(engine=GEMINI, success=True, cost=0.005) for _ in range(3)] + [
        _record(engine=GEMINI, success=False, cost=0.005, error="rate limit"),
    ]
    await _seed_records(exec_repo, records)

    prefs = await update_strategy.update_engine_preferences()
    assert len(prefs) >= 1

    gemini_pref = next(p for p in prefs if p.engine == GEMINI)
    assert gemini_pref.success_rate == pytest.approx(0.75, abs=0.01)
    assert gemini_pref.sample_count == 4

    loaded = strategy_store.load_engine_preferences()
    assert len(loaded) >= 1


# ===========================================================================
# Test 6: Recovery rule extraction
# ===========================================================================


async def test_recovery_rule_extraction(
    exec_repo: InMemoryExecutionRecordRepository,
    update_strategy: UpdateStrategyUseCase,
    strategy_store: StrategyStore,
) -> None:
    """Recovery rules extracted from failure→success pairs."""
    records = [
        # 2+ failures with same error on CLAUDE
        _record(
            engine=CLAUDE,
            success=False,
            error="docker: Cannot connect to daemon",
            task_type=TaskType.LONG_RUNNING_DEV,
        ),
        _record(
            engine=CLAUDE,
            success=False,
            error="docker: Cannot connect to daemon",
            task_type=TaskType.LONG_RUNNING_DEV,
        ),
        # Success on different engine for same task type
        _record(
            engine=GEMINI,
            success=True,
            task_type=TaskType.LONG_RUNNING_DEV,
        ),
    ]
    await _seed_records(exec_repo, records)

    rules = await update_strategy.update_recovery_rules()
    assert len(rules) >= 1

    rule = rules[0]
    assert "docker" in rule.error_pattern.lower()
    assert rule.failed_tool == CLAUDE.value
    assert rule.alternative_tool == GEMINI.value

    # Verify JSONL persistence
    loaded = strategy_store.load_recovery_rules()
    assert len(loaded) >= 1


# ===========================================================================
# Test 7: Strategy store JSONL round-trip
# ===========================================================================


async def test_strategy_store_jsonl_roundtrip(
    strategy_store: StrategyStore,
) -> None:
    """JSONL files can be written and re-read exactly."""
    from domain.entities.strategy import EnginePreference, ModelPreference

    model_prefs = [
        ModelPreference(
            task_type=TaskType.CODE_GENERATION,
            model="claude-sonnet-4-6",
            success_rate=0.85,
            avg_cost_usd=0.02,
            avg_duration_seconds=3.5,
            sample_count=20,
        ),
    ]
    engine_prefs = [
        EnginePreference(
            task_type=TaskType.SIMPLE_QA,
            engine=OLLAMA,
            success_rate=0.90,
            avg_cost_usd=0.0,
            avg_duration_seconds=1.2,
            sample_count=50,
        ),
    ]
    rules = [
        RecoveryRule(
            error_pattern="timeout",
            failed_tool="claude_code",
            alternative_tool="ollama",
            success_count=5,
            total_attempts=7,
        ),
    ]

    strategy_store.save_model_preferences(model_prefs)
    strategy_store.save_engine_preferences(engine_prefs)
    strategy_store.save_recovery_rules(rules)

    loaded_models = strategy_store.load_model_preferences()
    assert len(loaded_models) == 1
    assert loaded_models[0].model == "claude-sonnet-4-6"
    assert loaded_models[0].success_rate == pytest.approx(0.85)

    loaded_engines = strategy_store.load_engine_preferences()
    assert len(loaded_engines) == 1
    assert loaded_engines[0].engine == OLLAMA

    loaded_rules = strategy_store.load_recovery_rules()
    assert len(loaded_rules) == 1
    assert loaded_rules[0].success_rate == pytest.approx(5 / 7, abs=0.01)


# ===========================================================================
# Test 8: Full Level 2 update
# ===========================================================================


async def test_full_level2_update(
    exec_repo: InMemoryExecutionRecordRepository,
    update_strategy: UpdateStrategyUseCase,
) -> None:
    """run_full_update() combines model + engine + recovery."""
    records = []
    # 5 success + 2 failure on Claude for CODE_GENERATION
    for _ in range(5):
        records.append(_record(engine=CLAUDE, model="claude-sonnet-4-6", success=True))
    for _ in range(2):
        records.append(
            _record(
                engine=CLAUDE,
                model="claude-sonnet-4-6",
                success=False,
                error="rate_limit_exceeded",
            )
        )
    # 3 success on Ollama for same task type (recovery candidate)
    for _ in range(3):
        records.append(_record(engine=OLLAMA, model="qwen3:8b", success=True, cost=0.0))
    await _seed_records(exec_repo, records)

    result = await update_strategy.run_full_update()
    assert result.model_preferences_updated >= 1
    assert result.engine_preferences_updated >= 1
    assert len(result.details) >= 2


# ===========================================================================
# Test 9: Tool gap detection
# ===========================================================================


async def test_tool_gap_detection(
    exec_repo: InMemoryExecutionRecordRepository,
    systemic: SystemicEvolutionUseCase,
) -> None:
    """Recurring failures (3+) are detected as tool gaps."""
    # Same error 5 times → definite gap
    for _ in range(5):
        await exec_repo.save(
            _record(
                success=False,
                error="FileNotFoundError: No such file or directory",
            )
        )
    # Different error 2 times → NOT a gap (below threshold)
    for _ in range(2):
        await exec_repo.save(_record(success=False, error="ValueError: bad input"))

    gaps = await systemic.identify_tool_gaps()
    assert len(gaps) >= 1
    assert any("FileNotFoundError" in g for g in gaps)
    # ValueError should not appear (count < 3)
    assert not any("ValueError" in g for g in gaps)


# ===========================================================================
# Test 10: Full Level 3 evolution report
# ===========================================================================


async def test_full_evolution_report(
    exec_repo: InMemoryExecutionRecordRepository,
    systemic: SystemicEvolutionUseCase,
) -> None:
    """Full evolution produces a structured report."""
    records = []
    # Enough data for Level 2 preferences
    for _ in range(5):
        records.append(_record(engine=CLAUDE, model="claude-sonnet-4-6", success=True, cost=0.02))
    for _ in range(3):
        records.append(_record(engine=OLLAMA, model="qwen3:8b", success=True, cost=0.0))
    # Repeated failures for Level 3 gap detection
    for _ in range(4):
        records.append(
            _record(
                success=False,
                error="docker: daemon not running",
                engine=CLAUDE,
            )
        )
    await _seed_records(exec_repo, records)

    report = await systemic.run_evolution()

    assert report.level == EvolutionLevel.SYSTEMIC
    assert report.strategy_update is not None
    assert report.strategy_update.model_preferences_updated >= 1
    assert report.tool_gaps_found >= 1
    assert len(report.summary) > 0
    assert report.created_at is not None


# ===========================================================================
# Test 11: Fractal learning integration with evolution
# ===========================================================================


async def test_fractal_learning_with_evolution(
    exec_repo: InMemoryExecutionRecordRepository,
    analyze: AnalyzeExecutionUseCase,
) -> None:
    """ErrorPattern data from FractalLearner can coexist with evolution data."""
    from domain.entities.fractal_learning import ErrorPattern, SuccessfulPath
    from infrastructure.fractal.in_memory_learning_repo import (
        InMemoryFractalLearningRepository,
    )

    learning_repo = InMemoryFractalLearningRepository()

    # Record execution failures
    for _ in range(3):
        await exec_repo.save(_record(success=False, error="ImportError: No module named 'foo'"))

    # Also record in fractal learning repo
    pattern = ErrorPattern(
        goal_fragment="install package",
        node_description="execute pip install",
        error_message="ImportError: No module named 'foo'",
    )
    await learning_repo.save_error_pattern(pattern)

    path = SuccessfulPath(
        goal_fragment="install package",
        node_descriptions=["execute pip install", "verify import"],
        total_cost_usd=0.0,
    )
    await learning_repo.save_successful_path(path)

    # Both systems see the data
    exec_patterns = await analyze.get_failure_patterns()
    assert len(exec_patterns) >= 1

    learning_patterns = await learning_repo.find_error_patterns_by_goal("install package")
    assert len(learning_patterns) >= 1

    learning_paths = await learning_repo.find_successful_paths("install package")
    assert len(learning_paths) >= 1


# ===========================================================================
# Test 12: Evolution with empty history
# ===========================================================================


async def test_evolution_with_empty_history(
    systemic: SystemicEvolutionUseCase,
) -> None:
    """Evolution handles empty execution history gracefully."""
    report = await systemic.run_evolution()

    assert report.level == EvolutionLevel.SYSTEMIC
    assert report.strategy_update is not None
    assert report.strategy_update.model_preferences_updated == 0
    assert report.strategy_update.engine_preferences_updated == 0
    assert report.strategy_update.recovery_rules_added == 0
    assert report.tool_gaps_found == 0
    assert "No changes" in report.summary


# ===========================================================================
# Test 13: Model distribution analysis
# ===========================================================================


async def test_model_distribution(
    exec_repo: InMemoryExecutionRecordRepository,
    analyze: AnalyzeExecutionUseCase,
) -> None:
    """Model distribution reflects actual usage."""
    records = [
        _record(model="claude-sonnet-4-6"),
        _record(model="claude-sonnet-4-6"),
        _record(model="claude-sonnet-4-6"),
        _record(model="qwen3:8b", engine=OLLAMA),
        _record(model="gemini-2.5-flash", engine=GEMINI),
    ]
    await _seed_records(exec_repo, records)

    dist = await analyze.get_model_distribution()
    assert dist["claude-sonnet-4-6"] == 3
    assert dist["qwen3:8b"] == 1
    assert dist["gemini-2.5-flash"] == 1


# ===========================================================================
# Test 14: Strategy store append rule
# ===========================================================================


async def test_strategy_store_append_rule(
    strategy_store: StrategyStore,
) -> None:
    """Append-only JSONL preserves all rules."""
    rule1 = RecoveryRule(
        error_pattern="timeout",
        alternative_tool="ollama",
        success_count=1,
        total_attempts=1,
    )
    rule2 = RecoveryRule(
        error_pattern="rate_limit",
        alternative_tool="gemini_cli",
        success_count=2,
        total_attempts=3,
    )

    strategy_store.append_recovery_rule(rule1)
    strategy_store.append_recovery_rule(rule2)

    loaded = strategy_store.load_recovery_rules()
    assert len(loaded) == 2
    assert loaded[0].error_pattern == "timeout"
    assert loaded[1].error_pattern == "rate_limit"


# ===========================================================================
# Test 15: Stats filtered by task type
# ===========================================================================


async def test_stats_filtered_by_task_type(
    exec_repo: InMemoryExecutionRecordRepository,
    analyze: AnalyzeExecutionUseCase,
) -> None:
    """Stats can be filtered to a single task type."""
    records = [
        _record(task_type=TaskType.CODE_GENERATION, success=True, cost=0.02),
        _record(task_type=TaskType.CODE_GENERATION, success=False, cost=0.01),
        _record(task_type=TaskType.SIMPLE_QA, success=True, cost=0.0),
    ]
    await _seed_records(exec_repo, records)

    code_stats = await analyze.get_stats(task_type=TaskType.CODE_GENERATION)
    assert code_stats.total_count == 2
    assert code_stats.success_rate == pytest.approx(0.5)

    qa_stats = await analyze.get_stats(task_type=TaskType.SIMPLE_QA)
    assert qa_stats.total_count == 1
    assert qa_stats.success_rate == pytest.approx(1.0)
