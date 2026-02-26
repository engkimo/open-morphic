"""CostEstimator — estimates per-subtask cost from model pricing and token heuristics."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostEstimate:
    """Cost estimate for a single subtask."""

    description: str
    model: str
    estimated_tokens: int
    estimated_cost_usd: float


# Cost per 1M tokens (input). Approximate pricing.
MODEL_COST_TABLE: dict[str, float] = {
    # Free (local)
    "ollama/qwen3:8b": 0.0,
    "ollama/qwen3-coder:30b": 0.0,
    "ollama/deepseek-r1:8b": 0.0,
    "ollama/llama3.2:3b": 0.0,
    "ollama/phi4:14b": 0.0,
    # Low tier
    "claude-haiku-4-5-20251001": 0.25,
    "gemini/gemini-2.0-flash": 0.10,
    # Medium tier
    "claude-sonnet-4-6": 3.00,
    "gpt-4o-mini": 0.15,
    "gemini/gemini-2.5-pro": 1.25,
    # High tier
    "claude-opus-4-6": 15.00,
    "gpt-4o": 2.50,
}

# Default token estimate per subtask complexity
DEFAULT_TOKENS_PER_SUBTASK = 2000


class CostEstimator:
    """Estimate cost for a set of subtask descriptions given a model."""

    def __init__(self, cost_table: dict[str, float] | None = None) -> None:
        self._cost_table = cost_table or MODEL_COST_TABLE

    def estimate(
        self,
        subtask_descriptions: list[str],
        model: str = "ollama/qwen3:8b",
        tokens_per_subtask: int = DEFAULT_TOKENS_PER_SUBTASK,
    ) -> list[CostEstimate]:
        """Estimate cost for each subtask."""
        cost_per_m = self._get_cost_per_m(model)
        results = []
        for desc in subtask_descriptions:
            # Scale tokens by description length (heuristic)
            token_estimate = max(tokens_per_subtask, len(desc) * 4)
            cost = (token_estimate / 1_000_000) * cost_per_m
            results.append(
                CostEstimate(
                    description=desc,
                    model=model,
                    estimated_tokens=token_estimate,
                    estimated_cost_usd=round(cost, 6),
                )
            )
        return results

    def estimate_total(
        self,
        subtask_descriptions: list[str],
        model: str = "ollama/qwen3:8b",
    ) -> float:
        """Return total estimated cost for all subtasks."""
        estimates = self.estimate(subtask_descriptions, model)
        return sum(e.estimated_cost_usd for e in estimates)

    def is_within_budget(
        self,
        subtask_descriptions: list[str],
        model: str,
        budget_usd: float,
    ) -> bool:
        """Check if estimated cost fits within budget."""
        return self.estimate_total(subtask_descriptions, model) <= budget_usd

    def _get_cost_per_m(self, model: str) -> float:
        """Get cost per 1M tokens for a model. Local models are always $0."""
        if model.startswith("ollama/"):
            return 0.0
        return self._cost_table.get(model, 3.0)  # Default to medium tier
