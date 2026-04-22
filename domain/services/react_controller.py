"""ReactController — pure iteration control logic for ReAct loops.

No I/O, no external dependencies. Stateless utility functions.
"""

from __future__ import annotations

from typing import Any


class ReactController:
    """Pure functions governing ReAct loop control flow."""

    @staticmethod
    def should_continue(
        step_count: int,
        max_iterations: int,
        has_tool_calls: bool,
        has_final_answer: bool,
    ) -> tuple[bool, str]:
        """Decide whether the ReAct loop should continue.

        Returns:
            (should_continue, reason) where reason is one of:
            "continue", "final_answer", "max_iterations", "no_action"
        """
        if has_final_answer and not has_tool_calls:
            return False, "final_answer"
        if step_count >= max_iterations:
            return False, "max_iterations"
        if has_tool_calls:
            return True, "continue"
        # No tool calls and no final answer — treat as final answer
        return False, "final_answer"

    @staticmethod
    def build_tool_result_message(
        tool_call_id: str,
        tool_name: str,
        result: str,
    ) -> dict[str, Any]:
        """Build a tool result message in OpenAI chat format."""
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result,
        }
