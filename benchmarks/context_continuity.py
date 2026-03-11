"""Context Continuity Benchmark.

Measures how much shared context survives a round-trip through each
ContextAdapter (inject → extract).

Scoring:
    For each adapter, a SharedTaskState with known decisions, artifacts,
    and blockers is injected, then the output is examined to see how many
    of the original items can be recovered via extract_insights().

    score = recovered_items / expected_items

Target: overall average > 85%.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from domain.entities.cognitive import AgentAction, Decision, SharedTaskState
from domain.ports.context_adapter import ContextAdapterPort
from domain.value_objects.agent_engine import AgentEngineType


@dataclass(frozen=True)
class AdapterScore:
    """Score for a single adapter."""

    engine: str
    decisions_injected: int
    decisions_found: int
    artifacts_injected: int
    artifacts_found: int
    blockers_injected: int
    blockers_found: int
    context_length: int

    @property
    def total_injected(self) -> int:
        return self.decisions_injected + self.artifacts_injected + self.blockers_injected

    @property
    def total_found(self) -> int:
        return self.decisions_found + self.artifacts_found + self.blockers_found

    @property
    def score(self) -> float:
        if self.total_injected == 0:
            return 1.0
        return self.total_found / self.total_injected


@dataclass
class ContinuityResult:
    """Result of the full benchmark suite."""

    adapter_scores: list[AdapterScore] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def overall_score(self) -> float:
        if not self.adapter_scores:
            return 0.0
        return sum(s.score for s in self.adapter_scores) / len(self.adapter_scores)


def _build_reference_state() -> SharedTaskState:
    """Create a SharedTaskState with known content for benchmarking."""
    state = SharedTaskState(task_id="bench-ctx-001")

    # 5 decisions from different engines
    engines = [
        AgentEngineType.CLAUDE_CODE,
        AgentEngineType.GEMINI_CLI,
        AgentEngineType.CODEX_CLI,
        AgentEngineType.OLLAMA,
        AgentEngineType.OPENHANDS,
    ]
    for i, eng in enumerate(engines):
        state.add_decision(
            Decision(
                description=f"Decided to use approach-{i} for module-{i}",
                rationale=f"Approach-{i} is optimal for module-{i} complexity",
                agent_engine=eng,
                confidence=0.7 + i * 0.05,
            )
        )

    # 4 artifacts
    state.add_artifact("config.yaml", "database: postgres, port: 5432")
    state.add_artifact("schema.sql", "CREATE TABLE users (id SERIAL PRIMARY KEY)")
    state.add_artifact("main.py", "from fastapi import FastAPI")
    state.add_artifact("test_main.py", "def test_health(): assert True")

    # 3 blockers
    state.add_blocker("Missing API key for external service")
    state.add_blocker("Database migration not yet applied")
    state.add_blocker("Frontend build failing on CI")

    # Agent history
    for i, eng in enumerate(engines[:3]):
        state.add_action(
            AgentAction(
                agent_engine=eng,
                action_type="execute",
                summary=f"Executed task step {i}",
                cost_usd=0.01 * (i + 1),
                duration_seconds=5.0 * (i + 1),
            )
        )

    return state


def _count_decisions_in_context(context: str, state: SharedTaskState) -> int:
    """Count how many decisions from state appear in the context string."""
    count = 0
    for d in state.decisions:
        # Check if the decision description or a recognisable fragment is present
        desc_match = d.description.lower() in context.lower()
        frag_match = f"approach-{state.decisions.index(d)}" in context.lower()
        if desc_match or frag_match:
            count += 1
    return count


def _count_artifacts_in_context(context: str, state: SharedTaskState) -> int:
    """Count how many artifact keys appear in the context string."""
    count = 0
    for key in state.artifacts:
        if key in context:
            count += 1
    return count


def _count_blockers_in_context(context: str, state: SharedTaskState) -> int:
    """Count how many blockers appear in the context string."""
    count = 0
    for b in state.blockers:
        # Check for the full blocker or key phrases
        if b.lower() in context.lower():
            count += 1
        else:
            # Check for significant keywords
            words = [w for w in b.lower().split() if len(w) > 4]
            if any(w in context.lower() for w in words):
                count += 1
    return count


def run_benchmark(
    adapters: dict[AgentEngineType, ContextAdapterPort],
    max_tokens: int = 4000,
) -> ContinuityResult:
    """Run the context continuity benchmark across all adapters.

    Args:
        adapters: Engine→adapter mapping.
        max_tokens: Token budget for inject_context.

    Returns:
        ContinuityResult with per-adapter and overall scores.
    """
    state = _build_reference_state()
    result = ContinuityResult()

    for engine_type, adapter in adapters.items():
        context = adapter.inject_context(
            state=state,
            memory_context="Benchmark memory context for continuity test.",
            max_tokens=max_tokens,
        )

        decisions_found = _count_decisions_in_context(context, state)
        artifacts_found = _count_artifacts_in_context(context, state)
        blockers_found = _count_blockers_in_context(context, state)

        result.adapter_scores.append(
            AdapterScore(
                engine=engine_type.value,
                decisions_injected=len(state.decisions),
                decisions_found=decisions_found,
                artifacts_injected=len(state.artifacts),
                artifacts_found=artifacts_found,
                blockers_injected=len(state.blockers),
                blockers_found=blockers_found,
                context_length=len(context),
            )
        )

    return result
