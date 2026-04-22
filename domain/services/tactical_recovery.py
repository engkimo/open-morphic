"""TacticalRecovery — Level 1 in-task error recovery using learned rules.

Pure domain logic — no I/O, no external dependencies.
When an action fails, this service finds a known alternative from recovery rules.
"""

from __future__ import annotations

import re

from domain.entities.execution import Action
from domain.entities.strategy import RecoveryRule


class TacticalRecovery:
    """Level 1: In-task error recovery using learned rules.

    Pure domain service — no async, no I/O.
    """

    @staticmethod
    def find_alternative(
        failed_action: Action,
        error_message: str,
        rules: list[RecoveryRule],
    ) -> Action | None:
        """Find a recovery alternative for a failed action.

        Matches rules by:
        1. error_pattern regex match against error_message
        2. failed_tool match (if specified in rule)

        Returns the best matching alternative Action, or None.
        """
        matching: list[RecoveryRule] = []

        for rule in rules:
            # Check error pattern match
            try:
                if not re.search(rule.error_pattern, error_message, re.IGNORECASE):
                    continue
            except re.error:
                # Invalid regex — treat as literal substring
                if rule.error_pattern.lower() not in error_message.lower():
                    continue

            # Check tool match (empty failed_tool means "match any tool")
            if rule.failed_tool and rule.failed_tool != failed_action.tool:
                continue

            matching.append(rule)

        if not matching:
            return None

        # Pick the best rule by success rate, then by sample size
        ranked = TacticalRecovery.rank_rules(matching)
        best = ranked[0]

        return Action(
            tool=best.alternative_tool,
            args=best.alternative_args,
            description=f"Recovery: {best.error_pattern} → {best.alternative_tool}",
            risk=failed_action.risk,
        )

    @staticmethod
    def create_rule_from_recovery(
        failed_action: Action,
        error_message: str,
        successful_action: Action,
    ) -> RecoveryRule:
        """Create a new recovery rule from a successful manual recovery.

        Called when a failed action is manually recovered by the user or agent.
        The successful alternative becomes a new rule for future failures.
        """
        # Extract a concise error pattern from the error message
        pattern = TacticalRecovery._extract_error_pattern(error_message)

        return RecoveryRule(
            error_pattern=pattern,
            failed_tool=failed_action.tool,
            alternative_tool=successful_action.tool,
            alternative_args=successful_action.args,
            success_count=1,
            total_attempts=1,
        )

    @staticmethod
    def rank_rules(rules: list[RecoveryRule]) -> list[RecoveryRule]:
        """Rank rules by success rate (descending), then sample size (descending)."""
        return sorted(
            rules,
            key=lambda r: (r.success_rate, r.total_attempts),
            reverse=True,
        )

    @staticmethod
    def _extract_error_pattern(error_message: str) -> str:
        """Extract a regex-friendly pattern from an error message.

        Takes the first line and removes variable parts (paths, numbers, etc.).
        """
        first_line = error_message.strip().split("\n")[0]

        # Truncate to reasonable length
        if len(first_line) > 100:
            first_line = first_line[:100]

        # Remove file paths
        first_line = re.sub(r"[/\\][\w./\\-]+", "<path>", first_line)

        # Remove specific numbers (port numbers, line numbers, etc.)
        first_line = re.sub(r"\b\d{2,}\b", r"\\d+", first_line)

        return first_line if first_line else "unknown_error"
