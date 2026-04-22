"""CollaborationMode — how multiple models should collaborate on a task."""

from __future__ import annotations

from enum import Enum


class CollaborationMode(str, Enum):
    """Collaboration strategy when multiple models are requested.

    Detected from keywords in the user's goal text by
    :class:`ModelPreferenceExtractor`.
    """

    PARALLEL = "parallel"
    COMPARISON = "comparison"
    DIVERSE = "diverse"
    AUTO = "auto"
