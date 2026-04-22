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
from domain.ports.embedding import EmbeddingPort
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
    timestamp: str = field(
        default_factory=lambda: datetime.now().isoformat(),
    )

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

# Paraphrased versions of shared facts (same meaning, different words)
_ENGINE_C_OUTPUT = """
Work finished.
PostgreSQL was chosen as the database backend.
The config.yaml file was created containing DB configuration.
FastAPI is being used for REST API endpoints.
Connection to port 5432 was refused.
Redis was selected for the caching layer.
A docker-compose.yml file was written with service configs.
"""


def _tokenize(text: str) -> set[str]:
    """Tokenize text into normalised words (lowercase, no punctuation)."""
    import re

    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w}


async def _merge_and_dedup(
    insights_a: list,
    insights_b: list,
    token_threshold: float = 0.6,
) -> tuple[int, int]:
    """Merge two insight lists and count unique by normalised content + token overlap."""
    all_insights = insights_a + insights_b
    kept: list[set[str]] = []
    kept_raw: list[str] = []
    for ins in all_insights:
        normalised = ins.content.strip().lower()
        if not normalised:
            continue
        tokens_new = _tokenize(normalised)
        is_dup = False
        for i, existing_tokens in enumerate(kept):
            # Exact match
            if normalised == kept_raw[i]:
                is_dup = True
                break
            # Token overlap (Jaccard)
            if not existing_tokens or not tokens_new:
                continue
            intersection = len(tokens_new & existing_tokens)
            union = len(tokens_new | existing_tokens)
            if union > 0 and intersection / union >= token_threshold:
                is_dup = True
                break
        if not is_dup:
            kept.append(tokens_new)
            kept_raw.append(normalised)
    return len(all_insights), len(kept_raw)


async def run_benchmark(
    adapters: dict[AgentEngineType, ContextAdapterPort],
    engine_a: AgentEngineType = AgentEngineType.CLAUDE_CODE,
    engine_b: AgentEngineType = AgentEngineType.GEMINI_CLI,
    embedding_port: EmbeddingPort | None = None,
) -> DedupResult:
    """Run the deduplication accuracy benchmark.

    Args:
        adapters: Engine→adapter mapping for InsightExtractor.
        engine_a: First engine to simulate.
        engine_b: Second engine to simulate.
        embedding_port: Optional embedding port for semantic dedup.

    Returns:
        DedupResult with per-scenario scores.
    """
    extractor = InsightExtractor(
        adapters=adapters,
        embedding_port=embedding_port,
    )
    result = DedupResult()

    # Scenario 1: Identical output from two engines
    insights_a = await extractor.extract_from_output(
        engine_a,
        _ENGINE_A_OUTPUT,
    )
    insights_b = await extractor.extract_from_output(
        engine_b,
        _ENGINE_B_OUTPUT,
    )
    total_raw, unique_count = await _merge_and_dedup(
        insights_a,
        insights_b,
    )

    result.scores.append(
        DedupScore(
            scenario="overlapping_facts",
            engine_a=engine_a.value,
            engine_b=engine_b.value,
            raw_count_a=len(insights_a),
            raw_count_b=len(insights_b),
            total_raw=total_raw,
            deduped_count=unique_count,
        )
    )

    # Scenario 2: Completely unique outputs
    unique_output_a = "Decided to implement caching with Redis. Created file cache.py."
    unique_output_b = "Chose to add logging middleware. Modified file main.py with logging setup."

    u_insights_a = await extractor.extract_from_output(
        engine_a,
        unique_output_a,
    )
    u_insights_b = await extractor.extract_from_output(
        engine_b,
        unique_output_b,
    )
    u_total, u_unique = await _merge_and_dedup(
        u_insights_a,
        u_insights_b,
    )

    result.scores.append(
        DedupScore(
            scenario="unique_outputs",
            engine_a=engine_a.value,
            engine_b=engine_b.value,
            raw_count_a=len(u_insights_a),
            raw_count_b=len(u_insights_b),
            total_raw=u_total,
            deduped_count=u_unique,
        )
    )

    # Scenario 3: Same fact, different phrasing (case variation)
    case_a = "Decided to use PostgreSQL for the database layer."
    case_b = "decided to use postgresql for the database layer."
    c_insights_a = await extractor.extract_from_output(engine_a, case_a)
    c_insights_b = await extractor.extract_from_output(engine_b, case_b)
    c_total, c_unique = await _merge_and_dedup(
        c_insights_a,
        c_insights_b,
    )

    result.scores.append(
        DedupScore(
            scenario="case_variation",
            engine_a=engine_a.value,
            engine_b=engine_b.value,
            raw_count_a=len(c_insights_a),
            raw_count_b=len(c_insights_b),
            total_raw=c_total,
            deduped_count=c_unique,
        )
    )

    # Scenario 4: Paraphrased facts (same meaning, different words)
    # Only effective with semantic dedup (embedding_port != None)
    p_insights_a = await extractor.extract_from_output(
        engine_a,
        _ENGINE_A_OUTPUT,
    )
    p_insights_c = await extractor.extract_from_output(
        engine_b,
        _ENGINE_C_OUTPUT,
    )
    p_total, p_unique = await _merge_and_dedup(
        p_insights_a,
        p_insights_c,
    )

    result.scores.append(
        DedupScore(
            scenario="paraphrased_facts",
            engine_a=engine_a.value,
            engine_b=engine_b.value,
            raw_count_a=len(p_insights_a),
            raw_count_b=len(p_insights_c),
            total_raw=p_total,
            deduped_count=p_unique,
        )
    )

    return result
