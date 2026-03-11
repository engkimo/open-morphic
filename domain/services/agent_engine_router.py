"""AgentEngineRouter — Pure domain service for engine selection.

Two-tier routing architecture:
  Tier 1 (this): AgentEngineRouter → picks execution ENGINE
  Tier 2 (existing): LiteLLMGateway → picks LLM MODEL (used internally by each engine)

Pure static methods, no I/O, no constructor dependencies.
Follows the same pattern as RiskAssessor and ApprovalEngine.
"""

from __future__ import annotations

from domain.entities.cognitive import AgentAffinityScore
from domain.services.agent_affinity import AgentAffinityScorer
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType

# TaskType → primary engine mapping (matches CLAUDE.md AGENT_ROUTING_MAP)
_PRIMARY_ENGINE_MAP: dict[TaskType, AgentEngineType] = {
    TaskType.LONG_RUNNING_DEV: AgentEngineType.OPENHANDS,
    TaskType.COMPLEX_REASONING: AgentEngineType.CLAUDE_CODE,
    TaskType.LONG_CONTEXT: AgentEngineType.GEMINI_CLI,
    TaskType.CODE_GENERATION: AgentEngineType.CODEX_CLI,
    TaskType.SIMPLE_QA: AgentEngineType.OLLAMA,
    TaskType.FILE_OPERATION: AgentEngineType.OLLAMA,
    TaskType.MULTIMODAL: AgentEngineType.CLAUDE_CODE,
    TaskType.WORKFLOW_PIPELINE: AgentEngineType.ADK,
}

# Engine → ordered fallback chain (OLLAMA is the ultimate fallback, never listed here)
_FALLBACK_CHAIN: dict[AgentEngineType, list[AgentEngineType]] = {
    AgentEngineType.OPENHANDS: [
        AgentEngineType.CLAUDE_CODE,
        AgentEngineType.CODEX_CLI,
        AgentEngineType.OLLAMA,
    ],
    AgentEngineType.CLAUDE_CODE: [
        AgentEngineType.CODEX_CLI,
        AgentEngineType.GEMINI_CLI,
        AgentEngineType.OLLAMA,
    ],
    AgentEngineType.GEMINI_CLI: [
        AgentEngineType.CLAUDE_CODE,
        AgentEngineType.OLLAMA,
    ],
    AgentEngineType.CODEX_CLI: [
        AgentEngineType.CLAUDE_CODE,
        AgentEngineType.OLLAMA,
    ],
    AgentEngineType.ADK: [
        AgentEngineType.GEMINI_CLI,
        AgentEngineType.CLAUDE_CODE,
        AgentEngineType.OLLAMA,
    ],
    AgentEngineType.OLLAMA: [],
}


class AgentEngineRouter:
    """Select the optimal agent execution engine for a task.

    Priority order:
      1. budget <= 0  → OLLAMA (always free)
      2. estimated_hours > 1  → OPENHANDS (Docker sandbox, long-running)
      3. context_tokens > 100_000  → GEMINI_CLI (2M token window)
      4. _PRIMARY_ENGINE_MAP[task_type]  → default for that task type
    """

    @staticmethod
    def select(
        task_type: TaskType,
        budget: float = 0.0,
        estimated_hours: float = 0.0,
        context_tokens: int = 0,
    ) -> AgentEngineType:
        """Select a single best engine based on task characteristics."""
        # Priority 1: No budget → OLLAMA (free)
        if budget <= 0:
            return AgentEngineType.OLLAMA

        # Priority 2: Long-running task → OPENHANDS (Docker sandbox)
        if estimated_hours > 1.0:
            return AgentEngineType.OPENHANDS

        # Priority 3: Large context → GEMINI_CLI (2M tokens)
        if context_tokens > 100_000:
            return AgentEngineType.GEMINI_CLI

        # Priority 4: Primary map lookup (default: CLAUDE_CODE)
        return _PRIMARY_ENGINE_MAP.get(task_type, AgentEngineType.CLAUDE_CODE)

    @staticmethod
    def get_fallback_chain(engine: AgentEngineType) -> list[AgentEngineType]:
        """Return an ordered list of fallback engines. Returns a copy."""
        return list(_FALLBACK_CHAIN.get(engine, []))

    @staticmethod
    def select_with_fallbacks(
        task_type: TaskType,
        budget: float = 0.0,
        estimated_hours: float = 0.0,
        context_tokens: int = 0,
    ) -> list[AgentEngineType]:
        """Select preferred engine + fallback chain, OLLAMA always last.

        Returns a deduplicated list: [preferred, ...fallbacks, OLLAMA].
        If budget <= 0, returns [OLLAMA] only.
        """
        preferred = AgentEngineRouter.select(
            task_type=task_type,
            budget=budget,
            estimated_hours=estimated_hours,
            context_tokens=context_tokens,
        )

        # budget=0 → only OLLAMA makes sense
        if budget <= 0:
            return [AgentEngineType.OLLAMA]

        # Build chain: preferred + fallbacks, deduplicated, OLLAMA last
        chain = [preferred]
        for fallback in AgentEngineRouter.get_fallback_chain(preferred):
            if fallback not in chain:
                chain.append(fallback)

        # Ensure OLLAMA is present and last
        if AgentEngineType.OLLAMA in chain:
            chain.remove(AgentEngineType.OLLAMA)
        chain.append(AgentEngineType.OLLAMA)

        return chain

    @staticmethod
    def select_with_affinity(
        task_type: TaskType,
        budget: float = 0.0,
        estimated_hours: float = 0.0,
        context_tokens: int = 0,
        affinities: list[AgentAffinityScore] | None = None,
        min_samples: int = 3,
        boost_threshold: float = 0.6,
    ) -> list[AgentEngineType]:
        """Select engines with affinity-aware reranking.

        1. Compute base chain via select_with_fallbacks()
        2. If budget <= 0 → return [OLLAMA] (unchanged)
        3. Rank affinity scores via AgentAffinityScorer.rank()
        4. If top engine scores >= boost_threshold and is in chain → promote to front
        5. If top engine not in chain but scores >= threshold → insert at position 1
        6. OLLAMA stays last, dedup preserved
        """
        base_chain = AgentEngineRouter.select_with_fallbacks(
            task_type=task_type,
            budget=budget,
            estimated_hours=estimated_hours,
            context_tokens=context_tokens,
        )

        # budget=0 → only OLLAMA
        if budget <= 0:
            return base_chain

        # No affinity data → return base chain
        if not affinities:
            return base_chain

        ranked = AgentAffinityScorer.rank(affinities, min_samples=min_samples)
        if not ranked:
            return base_chain

        top_engine, top_score = ranked[0]
        if top_score < boost_threshold:
            return base_chain

        # Build new chain with affinity-boosted engine at front
        new_chain: list[AgentEngineType] = [top_engine]
        for engine in base_chain:
            if engine not in new_chain:
                new_chain.append(engine)

        # Ensure OLLAMA is last
        if AgentEngineType.OLLAMA in new_chain:
            new_chain.remove(AgentEngineType.OLLAMA)
        new_chain.append(AgentEngineType.OLLAMA)

        return new_chain
