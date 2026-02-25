"""ApprovalMode — 3-tier user approval model for LAEE."""

from enum import Enum


class ApprovalMode(str, Enum):
    FULL_AUTO = "full-auto"                    # User accepts all risks
    CONFIRM_DESTRUCTIVE = "confirm-destructive" # Only confirm HIGH/CRITICAL
    CONFIRM_ALL = "confirm-all"                # Confirm everything except SAFE
