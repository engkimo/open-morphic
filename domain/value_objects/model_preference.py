"""ModelPreference — extracted model preferences from user goal text."""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.value_objects.collaboration_mode import CollaborationMode


@dataclass(frozen=True)
class ModelPreference:
    """Immutable result of model name extraction from goal text.

    Attributes:
        models: Tuple of LiteLLM-compatible model IDs.
        clean_goal: Goal text with model names removed.
        collaboration_mode: How multiple models should collaborate.
    """

    models: tuple[str, ...]
    clean_goal: str
    collaboration_mode: CollaborationMode = field(default=CollaborationMode.AUTO)

    @property
    def has_preferences(self) -> bool:
        return len(self.models) > 0

    @property
    def is_multi_model(self) -> bool:
        return len(self.models) > 1
