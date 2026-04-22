"""FractalLearner — extracts learning signals from fractal engine execution.

Sprint 15.7 (TD-105): Pure domain service. No infrastructure dependencies.
Extracts error patterns from failed nodes and successful paths from completed plans.
"""

from __future__ import annotations

from domain.entities.fractal_engine import PlanNode
from domain.entities.fractal_learning import ErrorPattern, SuccessfulPath
from domain.value_objects.status import SubTaskStatus


class FractalLearner:
    """Extracts learning data from fractal engine execution results.

    Pure functions — no I/O, no LLM calls.
    """

    @staticmethod
    def extract_error_patterns(
        goal: str,
        nodes: list[PlanNode],
    ) -> list[ErrorPattern]:
        """Extract error patterns from failed nodes.

        Each failed node with an error message produces one ErrorPattern.
        """
        patterns: list[ErrorPattern] = []
        for node in nodes:
            if node.status != SubTaskStatus.FAILED:
                continue
            error_msg = node.error or "Unknown error"
            # Extract a short fragment from the goal for matching
            goal_fragment = _extract_goal_fragment(goal)
            patterns.append(
                ErrorPattern(
                    goal_fragment=goal_fragment,
                    node_description=node.description,
                    error_message=error_msg,
                    nesting_level=node.nesting_level,
                )
            )
        return patterns

    @staticmethod
    def extract_successful_path(
        goal: str,
        nodes: list[PlanNode],
    ) -> SuccessfulPath | None:
        """Extract a successful path if all nodes succeeded.

        Returns None if any node failed.
        """
        if not nodes:
            return None

        all_ok = all(n.status in (SubTaskStatus.SUCCESS, SubTaskStatus.DEGRADED) for n in nodes)
        if not all_ok:
            return None

        goal_fragment = _extract_goal_fragment(goal)
        total_cost = sum(n.cost_usd for n in nodes)
        descriptions = [n.description for n in nodes]

        return SuccessfulPath(
            goal_fragment=goal_fragment,
            node_descriptions=descriptions,
            total_cost_usd=total_cost,
        )

    @staticmethod
    def merge_error_pattern(
        existing: ErrorPattern,
        new: ErrorPattern,
    ) -> ErrorPattern:
        """Merge a new error pattern into an existing one.

        Increments occurrence count and updates last_seen.
        """
        existing.increment()
        return existing

    @staticmethod
    def merge_successful_path(
        existing: SuccessfulPath,
        new: SuccessfulPath,
    ) -> SuccessfulPath:
        """Merge a new successful path into an existing one.

        Increments usage count, keeps lower cost.
        """
        existing.increment()
        if new.total_cost_usd < existing.total_cost_usd:
            existing.total_cost_usd = new.total_cost_usd
        return existing


def _extract_goal_fragment(goal: str, max_len: int = 80) -> str:
    """Extract a short, matchable fragment from a goal string.

    Takes the first sentence or max_len characters, whichever is shorter.
    """
    # Take first sentence
    for sep in (".", "。", "\n"):
        idx = goal.find(sep)
        if 0 < idx < max_len:
            return goal[:idx].strip()
    # Truncate if needed
    fragment = goal[:max_len].strip()
    return fragment if fragment else goal[:max_len]
