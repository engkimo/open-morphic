"""A2ARouter — pure routing logic for agent-to-agent messages.

Given an action and a set of available agents with affinity scores,
selects the best receiver. No I/O — depends only on domain types.
"""

from __future__ import annotations

from domain.entities.a2a import AgentDescriptor
from domain.entities.cognitive import AgentAffinityScore
from domain.value_objects.a2a import A2AAction
from domain.value_objects.agent_engine import AgentEngineType

# Action → preferred capability mapping
_ACTION_CAPABILITY: dict[A2AAction, str] = {
    A2AAction.SOLVE: "code",
    A2AAction.REVIEW: "review",
    A2AAction.SYNTHESIZE: "synthesize",
    A2AAction.DELEGATE: "delegate",
    A2AAction.CRITIQUE: "review",
    A2AAction.INFORM: "inform",
}


class A2ARouter:
    """Pure domain service: select the best receiver for an A2A action."""

    @staticmethod
    def select_receiver(
        action: A2AAction,
        candidates: list[AgentDescriptor],
        affinities: list[AgentAffinityScore] | None = None,
        exclude: AgentEngineType | None = None,
    ) -> AgentEngineType | None:
        """Pick the best engine for *action* from *candidates*.

        Strategy:
        1. Filter out *exclude* (the sender — don't route to yourself).
        2. Prefer agents whose capabilities match the action.
        3. If affinity scores are provided, pick the highest-scoring match.
        4. Fall back to first available candidate.

        Returns ``None`` when no suitable agent exists.
        """
        filtered = [c for c in candidates if c.engine_type != exclude]
        if not filtered:
            return None

        wanted_cap = _ACTION_CAPABILITY.get(action, "")

        # Partition: capable vs rest
        capable = [c for c in filtered if c.has_capability(wanted_cap)]
        pool = capable or filtered

        # If we have affinities, score and rank
        if affinities:
            aff_map: dict[AgentEngineType, float] = {}
            for a in affinities:
                aff_map[a.engine] = (
                    0.4 * a.familiarity
                    + 0.2 * a.recency
                    + 0.3 * a.success_rate
                    + 0.1 * a.cost_efficiency
                )
            scored = sorted(
                pool,
                key=lambda c: aff_map.get(c.engine_type, 0.0),
                reverse=True,
            )
            return scored[0].engine_type

        return pool[0].engine_type
