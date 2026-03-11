"""Memory Deduplication Accuracy Benchmark.

Measures whether the InsightExtractor correctly deduplicates identical
facts extracted from different agent engines.

Scenario:
    Two engines produce output containing the same facts/decisions.
    InsightExtractor should normalise and dedup so that duplicate content
    is stored only once.

Scoring:
    score = unique_insights / total_raw_insights_without_dedup
    Perfect dedup on N duplicates → score = 1/N per duplicate pair.
    We measure: 1 - (duplicates_remaining / total_raw).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from domain.ports.context_adapter import ContextAdapterPort
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.cognitive.insight_extractor import InsightExtractor


@dataclass(frozen=True)
class DedupScore:
    """Dedup accuracy for a single scenario."""

    scenario: str
    engine_a: str
    engine_b: str
    raw_count_a: int
    raw_count_b: int
    total_raw: int
    deduped_count: int

    @property
    def duplicates_removed(self) -> int:
        return self.total_raw - self.deduped_count

    @property
    def dedup_rate(self) -> float:
        """Fraction of duplicates removed. 1.0 = perfect dedup."""
        if self.total_raw <= 1:
            return 1.0
        expected_unique = max(self.raw_count_a, self.raw_count_b)
        max_removable = self.total_raw - expected_unique
        if max_removable <= 0:
            return 1.0
        return min(1.0, self.duplicates_removed / max_removable)


@dataclass
class DedupResult:
    """Full dedup benchmark result."""

    scores: list[DedupScore] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def overall_accuracy(self) -> float:
        if not self.scores:
            return 0.0
        return sum(s.dedup_rate for s in self.scores) / len(self.scores)


# Test outputs containing overlapping facts
_SHARED_FACTS = [
    "Decided to use PostgreSQL for the database layer.",
    "Created file config.yaml with database settings.",
    "The project uses FastAPI for the REST API.",
    "Error: connection refused on port 5432.",
]

_ENGINE_A_OUTPUT = """
Task completed successfully.
Decided to use PostgreSQL for the database layer.
Created file config.yaml with database settings.
The project uses FastAPI for the REST API.
Error: connection refused on port 5432.
Also decided to use Redis for caching.
Created file docker-compose.yml with service definitions.
"""

_ENGINE_B_OUTPUT = """
Analysis complete.
Decided to use PostgreSQL for the database layer.
Created file config.yaml with database settings.
The project uses FastAPI for the REST API.
Error: connection refused on port 5432.
Additionally chose SQLAlchemy as the ORM.
Modified file requirements.txt with new dependencies.
"""


async def run_benchmark(
    adapters: dict[AgentEngineType, ContextAdapterPort],
    engine_a: AgentEngineType = AgentEngineType.CLAUDE_CODE,
    engine_b: AgentEngineType = AgentEngineType.GEMINI_CLI,
) -> DedupResult:
    """Run the deduplication accuracy benchmark.

    Args:
        adapters: Engine→adapter mapping for InsightExtractor.
        engine_a: First engine to simulate.
        engine_b: Second engine to simulate.

    Returns:
        DedupResult with per-scenario scores.
    """
    extractor = InsightExtractor(adapters=adapters)
    result = DedupResult()

    # Scenario 1: Identical output from two engines
    insights_a = await extractor.extract_from_output(engine_a, _ENGINE_A_OUTPUT)
    insights_b = await extractor.extract_from_output(engine_b, _ENGINE_B_OUTPUT)

    # Combine and check for duplicates (normalised content)
    seen: set[str] = set()
    unique_count = 0
    all_insights = insights_a + insights_b
    for ins in all_insights:
        normalised = ins.content.strip().lower()
        if normalised not in seen:
            seen.add(normalised)
            unique_count += 1

    result.scores.append(
        DedupScore(
            scenario="overlapping_facts",
            engine_a=engine_a.value,
            engine_b=engine_b.value,
            raw_count_a=len(insights_a),
            raw_count_b=len(insights_b),
            total_raw=len(all_insights),
            deduped_count=unique_count,
        )
    )

    # Scenario 2: Completely unique outputs
    unique_output_a = "Decided to implement caching with Redis. Created file cache.py."
    unique_output_b = "Chose to add logging middleware. Modified file main.py with logging setup."

    u_insights_a = await extractor.extract_from_output(engine_a, unique_output_a)
    u_insights_b = await extractor.extract_from_output(engine_b, unique_output_b)

    u_seen: set[str] = set()
    u_unique = 0
    u_all = u_insights_a + u_insights_b
    for ins in u_all:
        normalised = ins.content.strip().lower()
        if normalised not in u_seen:
            u_seen.add(normalised)
            u_unique += 1

    result.scores.append(
        DedupScore(
            scenario="unique_outputs",
            engine_a=engine_a.value,
            engine_b=engine_b.value,
            raw_count_a=len(u_insights_a),
            raw_count_b=len(u_insights_b),
            total_raw=len(u_all),
            deduped_count=u_unique,
        )
    )

    # Scenario 3: Same fact, different phrasing (case variation)
    case_a = "Decided to use PostgreSQL for the database layer."
    case_b = "decided to use postgresql for the database layer."
    c_insights_a = await extractor.extract_from_output(engine_a, case_a)
    c_insights_b = await extractor.extract_from_output(engine_b, case_b)
    c_all = c_insights_a + c_insights_b
    c_seen: set[str] = set()
    c_unique = 0
    for ins in c_all:
        normalised = ins.content.strip().lower()
        if normalised not in c_seen:
            c_seen.add(normalised)
            c_unique += 1

    result.scores.append(
        DedupScore(
            scenario="case_variation",
            engine_a=engine_a.value,
            engine_b=engine_b.value,
            raw_count_a=len(c_insights_a),
            raw_count_b=len(c_insights_b),
            total_raw=len(c_all),
            deduped_count=c_unique,
        )
    )

    return result
