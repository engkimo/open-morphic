"""RiskLevel — 5-tier action risk classification."""

from enum import IntEnum


class RiskLevel(IntEnum):
    SAFE = 0  # Read-only, fully reversible (ls, cat, ps, screenshot)
    LOW = 1  # Reversible creation (mkdir, touch, open)
    MEDIUM = 2  # Modification (edit, brew install)
    HIGH = 3  # Deletion, process kill, config changes
    CRITICAL = 4  # Recursive delete, sudo, credential access
