"""OutputRequirement — classifies what type of output a goal demands."""

from __future__ import annotations

from enum import Enum


class OutputRequirement(str, Enum):
    """What kind of deliverable a goal requires.

    Used by Gate ② to verify that the execution result matches the
    expected output modality — not just textual quality.
    """

    TEXT = "text"               # Text answer is sufficient (default)
    FILE_ARTIFACT = "file"      # A file must be created (slide, report, image, etc.)
    CODE_ARTIFACT = "code"      # A code file must be produced
    DATA_ARTIFACT = "data"      # Data retrieval / structured analysis required
