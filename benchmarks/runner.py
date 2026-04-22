"""Unified benchmark runner — runs all benchmarks and returns combined results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from benchmarks.context_continuity import ContinuityResult
from benchmarks.context_continuity import run_benchmark as run_continuity
from benchmarks.dedup_accuracy import DedupResult
from benchmarks.dedup_accuracy import run_benchmark as run_dedup
from domain.ports.context_adapter import ContextAdapterPort
from domain.value_objects.agent_engine import AgentEngineType


@dataclass
class BenchmarkSuiteResult:
    """Combined result of all benchmark suites."""

    context_continuity: ContinuityResult | None = None
    dedup_accuracy: DedupResult | None = None
    overall_score: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-safe dictionary."""
        result: dict[str, Any] = {
            "overall_score": round(self.overall_score, 4),
            "timestamp": self.timestamp,
            "errors": self.errors,
        }
        if self.context_continuity:
            result["context_continuity"] = {
                "overall_score": round(self.context_continuity.overall_score, 4),
                "adapter_scores": [asdict(s) for s in self.context_continuity.adapter_scores],
            }
        if self.dedup_accuracy:
            result["dedup_accuracy"] = {
                "overall_accuracy": round(self.dedup_accuracy.overall_accuracy, 4),
                "scores": [asdict(s) for s in self.dedup_accuracy.scores],
            }
        return result


async def run_all(
    adapters: dict[AgentEngineType, ContextAdapterPort],
    max_tokens: int = 4000,
) -> BenchmarkSuiteResult:
    """Run all benchmarks and return combined results.

    Args:
        adapters: Engine→adapter mapping.
        max_tokens: Token budget for context continuity.

    Returns:
        BenchmarkSuiteResult with individual and overall scores.
    """
    result = BenchmarkSuiteResult()
    scores: list[float] = []

    # 1. Context continuity (sync)
    try:
        result.context_continuity = run_continuity(adapters, max_tokens=max_tokens)
        scores.append(result.context_continuity.overall_score)
    except Exception as exc:
        result.errors.append(f"context_continuity: {exc}")

    # 2. Dedup accuracy (async)
    try:
        result.dedup_accuracy = await run_dedup(adapters)
        scores.append(result.dedup_accuracy.overall_accuracy)
    except Exception as exc:
        result.errors.append(f"dedup_accuracy: {exc}")

    # Overall = average of all suite scores
    result.overall_score = sum(scores) / len(scores) if scores else 0.0

    return result
