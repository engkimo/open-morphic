"""AgentAffinityScorer — Pure domain service for engine-topic fitness scoring.

Weights: familiarity×0.40 + recency×0.25 + success_rate×0.20 + cost_efficiency×0.15
Pure static methods, no I/O, no constructor dependencies.
"""

from __future__ import annotations

from domain.entities.cognitive import AgentAffinityScore
from domain.value_objects.agent_engine import AgentEngineType

# Scoring weights
_W_FAMILIARITY: float = 0.40
_W_RECENCY: float = 0.25
_W_SUCCESS: float = 0.20
_W_COST: float = 0.15


class AgentAffinityScorer:
    """Score and rank engines by topic affinity."""

    @staticmethod
    def score(affinity: AgentAffinityScore) -> float:
        """Compute weighted affinity score in [0, 1]."""
        return (
            affinity.familiarity * _W_FAMILIARITY
            + affinity.recency * _W_RECENCY
            + affinity.success_rate * _W_SUCCESS
            + affinity.cost_efficiency * _W_COST
        )

    @staticmethod
    def rank(
        affinities: list[AgentAffinityScore],
        min_samples: int = 3,
    ) -> list[tuple[AgentEngineType, float]]:
        """Rank engines by score, filtering out those below min_samples.

        Returns list of (engine, score) sorted descending.
        """
        scored = [
            (a.engine, AgentAffinityScorer.score(a))
            for a in affinities
            if a.sample_count >= min_samples
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    @staticmethod
    def select_best(
        affinities: list[AgentAffinityScore],
        min_samples: int = 3,
    ) -> AgentEngineType | None:
        """Select the highest-scoring engine, or None if no candidates."""
        ranked = AgentAffinityScorer.rank(affinities, min_samples=min_samples)
        if not ranked:
            return None
        return ranked[0][0]
