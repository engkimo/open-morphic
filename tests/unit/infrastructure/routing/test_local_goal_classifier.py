"""Tests for LocalGoalClassifier Ollama adapter (T070 RED).

Implementation choice: ``LocalGoalClassifier`` reuses ``LLMGateway`` with the
``ollama/qwen3:8b`` model id. ``OllamaManagerPort`` is lifecycle-only (no
``generate`` method); generation flows through LiteLLM-via-Ollama which the
gateway already wraps. DI wiring may consult ``OllamaManagerPort.is_running()``
to pick this adapter, but the adapter itself does not import it.
"""

from __future__ import annotations

import pytest

from domain.ports.llm_gateway import LLMGateway, LLMResponse
from domain.value_objects.planner_model import PlannerModel
from infrastructure.routing._prompts import ClassificationParseError
from infrastructure.routing.local_goal_classifier import (
    LOCAL_GATEWAY_MODEL,
    LocalGoalClassifier,
)


class FakeOllamaGateway(LLMGateway):
    def __init__(
        self,
        *,
        content: str = "",
        reported_cost_usd: float = 0.0,
    ) -> None:
        self._content = content
        self._cost = reported_cost_usd
        self.calls: list[tuple[list[dict], str | None]] = []

    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        self.calls.append((messages, model))
        return LLMResponse(
            content=self._content,
            model=model or LOCAL_GATEWAY_MODEL,
            prompt_tokens=100,
            completion_tokens=30,
            cost_usd=self._cost,
        )

    async def is_available(self, model: str) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return [LOCAL_GATEWAY_MODEL]


class TestLocalGoalClassifierHappyPath:
    @pytest.mark.asyncio
    async def test_returns_classification(self) -> None:
        gw = FakeOllamaGateway(
            content='{"model": "sonnet", "confidence": 0.85, "reason": "japanese"}'
        )
        clf = LocalGoalClassifier(gateway=gw)

        result = await clf.classify("東京駅から京都")

        assert result.model is PlannerModel.SONNET
        assert result.confidence == 0.85
        assert result.cost_usd == 0.0
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_uses_qwen3_8b_model_id(self) -> None:
        gw = FakeOllamaGateway(
            content='{"model": "haiku", "confidence": 0.9, "reason": "x"}'
        )
        clf = LocalGoalClassifier(gateway=gw)
        await clf.classify("goal")

        assert len(gw.calls) == 1
        _, model = gw.calls[0]
        assert model == LOCAL_GATEWAY_MODEL
        assert model == "ollama/qwen3:8b"

    @pytest.mark.asyncio
    async def test_cost_forced_zero_even_if_gateway_reports_nonzero(self) -> None:
        # Defensive: Ollama is local-only; cost MUST be 0.0 in the verdict
        # regardless of any non-zero figure the gateway might surface.
        gw = FakeOllamaGateway(
            content='{"model": "haiku", "confidence": 0.9, "reason": "x"}',
            reported_cost_usd=0.123,
        )
        clf = LocalGoalClassifier(gateway=gw)
        result = await clf.classify("goal")
        assert result.cost_usd == 0.0

    @pytest.mark.asyncio
    async def test_strips_qwen3_think_block(self) -> None:
        gw = FakeOllamaGateway(
            content=(
                "<think>The goal is in Japanese, route to sonnet.</think>\n"
                '{"model": "sonnet", "confidence": 0.92, "reason": "japanese"}'
            )
        )
        clf = LocalGoalClassifier(gateway=gw)
        result = await clf.classify("日本語のゴール")
        assert result.model is PlannerModel.SONNET


class TestLocalGoalClassifierParseError:
    @pytest.mark.asyncio
    async def test_malformed_output_raises(self) -> None:
        gw = FakeOllamaGateway(content="totally not JSON, mate")
        clf = LocalGoalClassifier(gateway=gw)
        with pytest.raises(ClassificationParseError):
            await clf.classify("goal")


class TestLocalGoalClassifierEmptyGoal:
    @pytest.mark.asyncio
    async def test_empty_rejected(self) -> None:
        gw = FakeOllamaGateway(
            content='{"model": "haiku", "confidence": 0.9, "reason": "x"}'
        )
        clf = LocalGoalClassifier(gateway=gw)
        with pytest.raises(ValueError):
            await clf.classify("")
