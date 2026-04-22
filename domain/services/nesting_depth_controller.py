"""NestingDepthController — max depth and termination logic for fractal engine.

Sprint 15.1: Controls recursion depth to prevent infinite nesting.
Considers max depth, cost budget, and node complexity to decide whether
a node should be expanded into a sub-engine or treated as terminal.
No I/O, no external dependencies. Stateless utility functions.
"""

from __future__ import annotations

DEFAULT_MAX_DEPTH = 5


class NestingDepthController:
    """Pure functions for controlling fractal engine recursion depth."""

    @staticmethod
    def can_expand(
        nesting_level: int,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> bool:
        """Check if further expansion is allowed at this nesting level."""
        return nesting_level < max_depth

    @staticmethod
    def should_terminate(
        nesting_level: int,
        is_terminal: bool,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> tuple[bool, str]:
        """Determine if a node should be treated as terminal.

        Returns:
            (is_terminal, reason) where reason explains the decision.
        """
        if is_terminal:
            return True, "node_marked_terminal"
        if nesting_level >= max_depth:
            return True, "max_depth_reached"
        return False, "expandable"

    @staticmethod
    def check_budget(
        accumulated_cost_usd: float,
        budget_usd: float,
    ) -> tuple[bool, str]:
        """Check if the cost budget allows further expansion.

        Returns:
            (within_budget, reason)
        """
        if budget_usd <= 0:
            return True, "no_budget_limit"
        if accumulated_cost_usd >= budget_usd:
            return False, "budget_exhausted"
        remaining_ratio = (budget_usd - accumulated_cost_usd) / budget_usd
        if remaining_ratio < 0.1:
            return False, "budget_nearly_exhausted"
        return True, "within_budget"

    @staticmethod
    def check_reflection_allowed(
        reflection_rounds: int,
        max_reflection_rounds: int,
        total_nodes: int,
        max_total_nodes: int,
        accumulated_cost_usd: float = 0.0,
        budget_usd: float = 0.0,
    ) -> tuple[bool, str]:
        """Check whether a reflection cycle is allowed.

        Guards against infinite expansion by limiting rounds, total nodes,
        and cost budget.

        Returns:
            (allowed, reason)
        """
        if reflection_rounds >= max_reflection_rounds:
            return False, "max_reflection_rounds_reached"
        if total_nodes >= max_total_nodes:
            return False, "max_total_nodes_reached"
        if budget_usd > 0 and accumulated_cost_usd >= budget_usd:
            return False, "budget_exhausted"
        return True, "reflection_allowed"
