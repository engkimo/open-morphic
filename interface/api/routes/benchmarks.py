"""Benchmark API routes — Sprint 7.6."""

from __future__ import annotations

from fastapi import APIRouter, Request

from interface.api.schemas import BenchmarkResultResponse

router = APIRouter(prefix="/api/benchmarks", tags=["benchmarks"])


@router.post("/run", response_model=BenchmarkResultResponse)
async def run_benchmarks(request: Request) -> BenchmarkResultResponse:
    """Run all benchmarks and return combined results."""
    from benchmarks.runner import run_all

    container = request.app.state.container
    adapters = container._context_adapters
    result = await run_all(adapters)
    return BenchmarkResultResponse.from_result(result)


@router.post("/continuity", response_model=BenchmarkResultResponse)
async def run_continuity_benchmark(request: Request) -> BenchmarkResultResponse:
    """Run context continuity benchmark only."""
    from benchmarks.context_continuity import run_benchmark
    from benchmarks.runner import BenchmarkSuiteResult

    container = request.app.state.container
    adapters = container._context_adapters
    continuity = run_benchmark(adapters)
    suite = BenchmarkSuiteResult(
        context_continuity=continuity,
        overall_score=continuity.overall_score,
    )
    return BenchmarkResultResponse.from_result(suite)


@router.post("/dedup", response_model=BenchmarkResultResponse)
async def run_dedup_benchmark(request: Request) -> BenchmarkResultResponse:
    """Run memory dedup accuracy benchmark only."""
    from benchmarks.dedup_accuracy import run_benchmark
    from benchmarks.runner import BenchmarkSuiteResult

    container = request.app.state.container
    adapters = container._context_adapters
    dedup = await run_benchmark(adapters)
    suite = BenchmarkSuiteResult(
        dedup_accuracy=dedup,
        overall_score=dedup.overall_accuracy,
    )
    return BenchmarkResultResponse.from_result(suite)
