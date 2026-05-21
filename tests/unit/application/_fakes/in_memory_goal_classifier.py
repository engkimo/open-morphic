"""Configurable fake GoalClassifierPort for unit tests.

Per TD-187, test code may import port-compliant `InMemory*` adapters from
`infrastructure/`. The goal-classifier-router pilot follows the council pilot
convention and keeps its fake under `tests/unit/application/_fakes/` so the
production adapter (LLM/Ollama-backed) can grow features independently.
"""

from __future__ import annotations

from collections import deque

from domain.ports.goal_classifier import GoalClassifierPort
from domain.value_objects.goal_classification import GoalClassification


class InMemoryGoalClassifier(GoalClassifierPort):
    """Test fake with a configurable response queue.

    - ``responses`` is consumed in FIFO order. When empty, ``default_response``
      is returned (or ``IndexError`` if no default was provided).
    - ``raise_on_call`` short-circuits before the queue is consumed and raises
      the supplied exception — use this to simulate classifier failures.
    - ``calls`` records every ``goal`` argument received, for assertions.
    """

    def __init__(
        self,
        *,
        responses: list[GoalClassification] | None = None,
        default_response: GoalClassification | None = None,
        raise_on_call: Exception | None = None,
    ) -> None:
        self._responses: deque[GoalClassification] = deque(responses or [])
        self._default_response = default_response
        self.raise_on_call = raise_on_call
        self.calls: list[str] = []

    async def classify(self, goal: str) -> GoalClassification:
        if not goal or not goal.strip():
            raise ValueError("goal must be non-empty")
        self.calls.append(goal)
        if self.raise_on_call is not None:
            raise self.raise_on_call
        if self._responses:
            return self._responses.popleft()
        if self._default_response is not None:
            return self._default_response
        raise IndexError(
            "InMemoryGoalClassifier exhausted: no responses queued and no default set"
        )
