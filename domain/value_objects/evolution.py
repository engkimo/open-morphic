"""EvolutionLevel — 3-tier self-evolution classification."""

from enum import Enum


class EvolutionLevel(str, Enum):
    TACTICAL = "tactical"  # Level 1: in-task recovery
    STRATEGIC = "strategic"  # Level 2: cross-session learning
    SYSTEMIC = "systemic"  # Level 3: tool gap filling
