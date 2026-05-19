"""Remote goal classifier — Anthropic Haiku 4.5 via ``LLMGateway``."""

from __future__ import annotations

import time

from domain.ports.goal_classifier import GoalClassifierPort
from domain.ports.llm_gateway import LLMGateway
from domain.value_objects.goal_classification import GoalClassification
from infrastructure.routing._prompts import SYSTEM_PROMPT, parse_classification

HAIKU_GATEWAY_MODEL = "claude-haiku-4-5-20251001"


class LLMGoalClassifier(GoalClassifierPort):
    """Pure-LLM goal classifier backed by a remote ``LLMGateway`` (Haiku 4.5)."""

    def __init__(
        self,
        *,
        gateway: LLMGateway,
        model_id: str = HAIKU_GATEWAY_MODEL,
        temperature: float = 0.0,
        max_tokens: int = 256,
    ) -> None:
        self._gateway = gateway
        self._model_id = model_id
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def classify(self, goal: str) -> GoalClassification:
        if not goal or not goal.strip():
            raise ValueError("goal must be non-empty")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"GOAL:\n{goal}"},
        ]

        start = time.perf_counter()
        response = await self._gateway.complete(
            messages=messages,
            model=self._model_id,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)

        return parse_classification(
            response.content,
            latency_ms=latency_ms,
            cost_usd=response.cost_usd,
        )
