"""ApprovalEngine — Pure domain service. Determines if an action needs user approval.

No infrastructure dependencies. Uses only domain value objects.
"""

from __future__ import annotations

from domain.value_objects import ApprovalMode, RiskLevel

# Approval matrix: mode → max auto-approved risk level
# Actions at or below this level are auto-approved.
# Actions above this level require user confirmation.
_AUTO_APPROVE_THRESHOLD: dict[ApprovalMode, RiskLevel] = {
    ApprovalMode.FULL_AUTO: RiskLevel.CRITICAL,  # Everything auto-approved
    ApprovalMode.CONFIRM_DESTRUCTIVE: RiskLevel.MEDIUM,  # HIGH+ needs confirmation
    ApprovalMode.CONFIRM_ALL: RiskLevel.SAFE,  # LOW+ needs confirmation
}


class ApprovalEngine:
    """Determine whether an action needs user approval based on mode and risk.

    Pure domain logic — no I/O, no UI interaction.
    The actual user prompt is handled by the infrastructure/interface layer.
    """

    def needs_approval(self, mode: ApprovalMode, risk: RiskLevel) -> bool:
        """Return True if the action requires user confirmation."""
        threshold = _AUTO_APPROVE_THRESHOLD[mode]
        return risk > threshold
