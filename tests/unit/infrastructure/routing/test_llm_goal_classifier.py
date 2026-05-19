"""Tests for LLMGoalClassifier remote adapter (T060 RED)."""

from __future__ import annotations

import pytest

from domain.ports.llm_gateway import LLMGateway, LLMResponse
from domain.value_objects.planner_model import PlannerModel
from infrastructure.routing._prompts import SYSTEM_PROMPT, ClassificationParseError
from infrastructure.routing.llm_goal_classifier import (
    HAIKU_GATEWAY_MODEL,
    LLMGoalClassifier,
)


class FakeLLMGateway(LLMGateway):
    def __init__(
        self,
        *,
        content: str = "",
        cost_usd: float = 0.0004,
        should_fail: bool = False,
    ) -> None:
        self._content = content
        self._cost = cost_usd
        self._should_fail = should_fail
        self.calls: list[tuple[list[dict], str | None]] = []

    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        self.calls.append((messages, model))
        if self._should_fail:
            raise RuntimeError("upstream failure")
        return LLMResponse(
            content=self._content,
            model=model or "haiku",
            prompt_tokens=120,
            completion_tokens=40,
            cost_usd=self._cost,
        )

    async def is_available(self, model: str) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return [HAIKU_GATEWAY_MODEL]


class TestLLMGoalClassifierHappyPath:
    @pytest.mark.asyncio
    async def test_returns_classification(self) -> None:
        gw = FakeLLMGateway(
            content='{"model": "haiku", "confidence": 0.9, "reason": "generic"}',
            cost_usd=0.0004,
        )
        clf = LLMGoalClassifier(gateway=gw)

        result = await clf.classify("Build a Python REST API")

        assert result.model is PlannerModel.HAIKU
        assert result.confidence == 0.9
        assert result.cost_usd == 0.0004
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_passes_haiku_model_id_to_gateway(self) -> None:
        gw = FakeLLMGateway(
            content='{"model": "haiku", "confidence": 0.9, "reason": "generic"}'
        )
        clf = LLMGoalClassifier(gateway=gw)
        await clf.classify("goal")

        assert len(gw.calls) == 1
        _, model = gw.calls[0]
        assert model == HAIKU_GATEWAY_MODEL

    @pytest.mark.asyncio
    async def test_uses_stable_system_prompt(self) -> None:
        gw = FakeLLMGateway(
            content='{"model": "haiku", "confidence": 0.9, "reason": "x"}'
        )
        clf = LLMGoalClassifier(gateway=gw)
        await clf.classify("anything")

        messages, _ = gw.calls[0]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_user_message_carries_goal_only(self) -> None:
        gw = FakeLLMGateway(
            content='{"model": "haiku", "confidence": 0.9, "reason": "x"}'
        )
        clf = LLMGoalClassifier(gateway=gw)
        await clf.classify("write a script")

        messages, _ = gw.calls[0]
        assert messages[-1]["role"] == "user"
        assert "write a script" in messages[-1]["content"]


class TestLLMGoalClassifierParseError:
    @pytest.mark.asyncio
    async def test_malformed_json_raises_parse_error(self) -> None:
        gw = FakeLLMGateway(content="not json at all")
        clf = LLMGoalClassifier(gateway=gw)

        with pytest.raises(ClassificationParseError):
            await clf.classify("goal")


class TestLLMGoalClassifierEmptyGoal:
    @pytest.mark.asyncio
    async def test_empty_goal_rejected(self) -> None:
        gw = FakeLLMGateway(
            content='{"model": "haiku", "confidence": 0.9, "reason": "x"}'
        )
        clf = LLMGoalClassifier(gateway=gw)
        with pytest.raises(ValueError):
            await clf.classify("")

    @pytest.mark.asyncio
    async def test_whitespace_goal_rejected(self) -> None:
        gw = FakeLLMGateway(
            content='{"model": "haiku", "confidence": 0.9, "reason": "x"}'
        )
        clf = LLMGoalClassifier(gateway=gw)
        with pytest.raises(ValueError):
            await clf.classify("   \n")
