"""Evolution routes — stats, failure patterns, preferences, strategy update, evolve."""

from __future__ import annotations

from fastapi import APIRouter, Request

from interface.api.schemas import (
    EnginePreferenceResponse,
    EvolutionReportResponse,
    ExecutionStatsResponse,
    FailurePatternResponse,
    FailurePatternsListResponse,
    ModelPreferenceResponse,
    PreferencesResponse,
    StrategyUpdateResponse,
)

router = APIRouter(prefix="/api/evolution", tags=["evolution"])


def _container(request: Request):  # type: ignore[no-untyped-def]
    return request.app.state.container


@router.get("/stats", response_model=ExecutionStatsResponse)
async def get_stats(request: Request, task_type: str | None = None) -> ExecutionStatsResponse:
    """Get execution statistics, optionally filtered by task type."""
    c = _container(request)
    tt = None
    if task_type:
        import contextlib

        from domain.value_objects.model_tier import TaskType

        with contextlib.suppress(ValueError):
            tt = TaskType(task_type)
    stats = await c.analyze_execution.get_stats(task_type=tt)
    return ExecutionStatsResponse(
        total_count=stats.total_count,
        success_count=stats.success_count,
        failure_count=stats.failure_count,
        success_rate=stats.success_rate,
        avg_cost_usd=stats.avg_cost_usd,
        avg_duration_seconds=stats.avg_duration_seconds,
        model_distribution=stats.model_distribution,
        engine_distribution=stats.engine_distribution,
    )


@router.get("/failures", response_model=FailurePatternsListResponse)
async def get_failures(request: Request, limit: int = 20) -> FailurePatternsListResponse:
    """Get recent failure patterns."""
    c = _container(request)
    patterns = await c.analyze_execution.get_failure_patterns(limit=limit)
    return FailurePatternsListResponse(
        patterns=[
            FailurePatternResponse(
                error_pattern=p.error_pattern,
                count=p.count,
                task_types=p.task_types,
                engines=p.engines,
            )
            for p in patterns
        ],
        count=len(patterns),
    )


@router.get("/preferences", response_model=PreferencesResponse)
async def get_preferences(request: Request) -> PreferencesResponse:
    """Get current learned model and engine preferences."""
    c = _container(request)
    model_prefs = c.strategy_store.load_model_preferences()
    engine_prefs = c.strategy_store.load_engine_preferences()
    return PreferencesResponse(
        model_preferences=[
            ModelPreferenceResponse(
                task_type=p.task_type.value,
                model=p.model,
                success_rate=p.success_rate,
                avg_cost_usd=p.avg_cost_usd,
                avg_duration_seconds=p.avg_duration_seconds,
                sample_count=p.sample_count,
            )
            for p in model_prefs
        ],
        engine_preferences=[
            EnginePreferenceResponse(
                task_type=p.task_type.value,
                engine=p.engine.value,
                success_rate=p.success_rate,
                avg_cost_usd=p.avg_cost_usd,
                avg_duration_seconds=p.avg_duration_seconds,
                sample_count=p.sample_count,
            )
            for p in engine_prefs
        ],
    )


@router.post("/update", response_model=StrategyUpdateResponse)
async def trigger_update(request: Request) -> StrategyUpdateResponse:
    """Trigger Level 2 strategy update."""
    c = _container(request)
    result = await c.update_strategy.run_full_update()
    return StrategyUpdateResponse(
        model_preferences_updated=result.model_preferences_updated,
        engine_preferences_updated=result.engine_preferences_updated,
        recovery_rules_added=result.recovery_rules_added,
        details=result.details,
    )


@router.post("/evolve", response_model=EvolutionReportResponse)
async def trigger_evolve(request: Request) -> EvolutionReportResponse:
    """Trigger full Level 3 evolution."""
    c = _container(request)
    report = await c.systemic_evolution.run_evolution()
    strategy = None
    if report.strategy_update:
        strategy = StrategyUpdateResponse(
            model_preferences_updated=report.strategy_update.model_preferences_updated,
            engine_preferences_updated=report.strategy_update.engine_preferences_updated,
            recovery_rules_added=report.strategy_update.recovery_rules_added,
            details=report.strategy_update.details,
        )
    return EvolutionReportResponse(
        level=report.level.value,
        strategy_update=strategy,
        tool_gaps_found=report.tool_gaps_found,
        tools_suggested=report.tools_suggested,
        summary=report.summary,
        created_at=report.created_at,
    )
