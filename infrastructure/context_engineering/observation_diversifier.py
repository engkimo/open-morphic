"""ObservationDiversifier — Manus Principle 5: maintain observation variety.

When similar observations repeat, LLMs drift by mimicking patterns.
Rotating serialization templates prevents this.
"""

from __future__ import annotations

from typing import Any

# Templates must be distinct to break pattern mimicry
_TEMPLATES = [
    "Result: {result}\nStatus: {status}",
    "Observation #{n}: {result} [{status}]",
    "Completed: {result} | State: {status}",
    "[{status}] >> {result} (step {n})",
]


class ObservationDiversifier:
    """Serialize observations using rotating templates to prevent LLM drift.

    Guarantee: N consecutive calls produce N distinct formats (up to len(templates)).
    """

    def __init__(self, templates: list[str] | None = None) -> None:
        self._templates = templates or list(_TEMPLATES)
        if len(self._templates) < 2:
            raise ValueError("At least 2 templates required for diversity")

    @property
    def template_count(self) -> int:
        return len(self._templates)

    def serialize(self, observation: dict[str, Any], step_index: int) -> str:
        """Format an observation using the template for step_index (mod N).

        Args:
            observation: dict with at least "result" and "status" keys.
            step_index: monotonically increasing index for template rotation.

        Returns:
            Formatted string using the selected template.
        """
        template = self._templates[step_index % len(self._templates)]
        return template.format(
            result=observation.get("result", ""),
            status=observation.get("status", ""),
            n=step_index,
        )

    def are_consecutive_diverse(self, observations: list[dict[str, Any]], start_index: int) -> bool:
        """Check that consecutive observations produce distinct formats."""
        seen: set[str] = set()
        for i, obs in enumerate(observations):
            fmt = self.serialize(obs, start_index + i)
            if fmt in seen:
                return False
            seen.add(fmt)
        return True
