"""Tests for LLMResultEvaluator — fractal engine Gate ② implementation.

Sprint 15.4: ~14 tests covering evaluation, JSON parsing, fallback behavior,
prompt construction, and decision-maker integration.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from domain.entities.fractal_engine import PlanNode, ResultEvaluation
from domain.ports.llm_gateway import LLMGateway, LLMResponse
from domain.value_objects.fractal_engine import ResultEvalDecision
from infrastructure.fractal.llm_result_evaluator import (
    LLMResultEvaluator,
    _clamp,
    _extract_json_object,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _llm_response(content: str, model: str = "test-model") -> LLMResponse:
    return LLMResponse(
        content=content,
        model=model,
        prompt_tokens=50,
        completion_tokens=30,
        cost_usd=0.0,
    )


def _eval_json(
    accuracy: float = 0.8,
    validity: float = 0.7,
    goal_alignment: float = 0.9,
    feedback: str = "Result looks good",
) -> str:
    return json.dumps(
        {
            "accuracy": accuracy,
            "validity": validity,
            "goal_alignment": goal_alignment,
            "feedback": feedback,
        }
    )


def _sample_node(
    description: str = "Fetch user data from API",
    nesting_level: int = 0,
    is_terminal: bool = True,
) -> PlanNode:
    return PlanNode(
        description=description,
        nesting_level=nesting_level,
        is_terminal=is_terminal,
    )


@pytest.fixture
def llm() -> AsyncMock:
    return AsyncMock(spec=LLMGateway)


@pytest.fixture
def evaluator(llm: AsyncMock) -> LLMResultEvaluator:
    return LLMResultEvaluator(llm, ok_threshold=0.7, retry_threshold=0.4)


# ===================================================================
# TestEvaluation — core evaluation flow
# ===================================================================


class TestEvaluation:
    """Core evaluation with decision-maker integration."""

    @pytest.mark.asyncio
    async def test_high_scores_return_ok(
        self, llm: AsyncMock, evaluator: LLMResultEvaluator
    ) -> None:
        llm.complete.return_value = _llm_response(_eval_json(0.9, 0.8, 0.85))
        node = _sample_node()

        result = await evaluator.evaluate(node, "Fetch user data", "user data response")

        assert isinstance(result, ResultEvaluation)
        assert result.accuracy == pytest.approx(0.9, abs=0.01)
        assert result.validity == pytest.approx(0.8, abs=0.01)
        assert result.goal_alignment == pytest.approx(0.85, abs=0.01)
        assert result.decision == ResultEvalDecision.OK

    @pytest.mark.asyncio
    async def test_medium_scores_return_retry(
        self, llm: AsyncMock, evaluator: LLMResultEvaluator
    ) -> None:
        llm.complete.return_value = _llm_response(_eval_json(0.5, 0.5, 0.5))
        node = _sample_node()

        result = await evaluator.evaluate(node, "Goal", "partial result")

        assert result.decision == ResultEvalDecision.RETRY

    @pytest.mark.asyncio
    async def test_low_scores_return_replan(
        self, llm: AsyncMock, evaluator: LLMResultEvaluator
    ) -> None:
        llm.complete.return_value = _llm_response(_eval_json(0.1, 0.2, 0.1))
        node = _sample_node()

        result = await evaluator.evaluate(node, "Goal", "bad result")

        assert result.decision == ResultEvalDecision.REPLAN

    @pytest.mark.asyncio
    async def test_node_id_preserved(self, llm: AsyncMock, evaluator: LLMResultEvaluator) -> None:
        llm.complete.return_value = _llm_response(_eval_json())
        node = _sample_node()

        result = await evaluator.evaluate(node, "Goal", "result")

        assert result.node_id == node.id

    @pytest.mark.asyncio
    async def test_feedback_preserved(self, llm: AsyncMock, evaluator: LLMResultEvaluator) -> None:
        llm.complete.return_value = _llm_response(_eval_json(feedback="Missing error handling"))
        node = _sample_node()

        result = await evaluator.evaluate(node, "Goal", "result")

        assert "Missing error handling" in result.feedback

    @pytest.mark.asyncio
    async def test_scores_clamped_to_valid_range(
        self, llm: AsyncMock, evaluator: LLMResultEvaluator
    ) -> None:
        payload = json.dumps(
            {"accuracy": 1.5, "validity": -0.3, "goal_alignment": 0.8, "feedback": ""}
        )
        llm.complete.return_value = _llm_response(payload)
        node = _sample_node()

        result = await evaluator.evaluate(node, "Goal", "result")

        assert result.accuracy == pytest.approx(1.0, abs=0.01)
        assert result.validity == pytest.approx(0.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_custom_thresholds(self, llm: AsyncMock) -> None:
        llm.complete.return_value = _llm_response(_eval_json(0.6, 0.6, 0.6))
        # With ok_threshold=0.5, overall=0.6 → OK
        evaluator = LLMResultEvaluator(llm, ok_threshold=0.5, retry_threshold=0.3)
        node = _sample_node()

        result = await evaluator.evaluate(node, "Goal", "result")

        assert result.decision == ResultEvalDecision.OK


# ===================================================================
# TestFallback
# ===================================================================


class TestFallback:
    """Fallback behavior on LLM failure or bad output."""

    @pytest.mark.asyncio
    async def test_invalid_json_returns_fallback(
        self, llm: AsyncMock, evaluator: LLMResultEvaluator
    ) -> None:
        llm.complete.return_value = _llm_response("Not valid JSON at all!!!")
        node = _sample_node()

        result = await evaluator.evaluate(node, "Goal", "result")

        assert result.accuracy == pytest.approx(0.5, abs=0.01)
        assert result.validity == pytest.approx(0.5, abs=0.01)
        assert result.goal_alignment == pytest.approx(0.5, abs=0.01)
        assert "Fallback" in result.feedback
        # With default thresholds (0.7/0.4), fallback scores 0.5 → RETRY
        assert result.decision == ResultEvalDecision.RETRY

    @pytest.mark.asyncio
    async def test_llm_exception_returns_fallback(
        self, llm: AsyncMock, evaluator: LLMResultEvaluator
    ) -> None:
        llm.complete.side_effect = RuntimeError("LLM unavailable")
        node = _sample_node()

        result = await evaluator.evaluate(node, "Goal", "result")

        assert result.accuracy == pytest.approx(0.5, abs=0.01)
        assert "Fallback" in result.feedback
        assert result.decision == ResultEvalDecision.RETRY

    @pytest.mark.asyncio
    async def test_fallback_decision_uses_configured_thresholds(self, llm: AsyncMock) -> None:
        """Fallback with low ok_threshold → fallback scores (0.5) get OK."""
        llm.complete.side_effect = RuntimeError("LLM down")
        evaluator = LLMResultEvaluator(llm, ok_threshold=0.4, retry_threshold=0.2)
        node = _sample_node()

        result = await evaluator.evaluate(node, "Goal", "result")

        assert result.decision == ResultEvalDecision.OK


# ===================================================================
# TestPromptConstruction
# ===================================================================


class TestPromptConstruction:
    """Verify prompt content passed to the LLM gateway."""

    @pytest.mark.asyncio
    async def test_goal_in_user_message(
        self, llm: AsyncMock, evaluator: LLMResultEvaluator
    ) -> None:
        llm.complete.return_value = _llm_response(_eval_json())
        node = _sample_node()

        await evaluator.evaluate(node, "Deploy microservices", "deployed successfully")

        messages = llm.complete.call_args[0][0]
        assert "Deploy microservices" in messages[1]["content"]

    @pytest.mark.asyncio
    async def test_node_description_in_user_message(
        self, llm: AsyncMock, evaluator: LLMResultEvaluator
    ) -> None:
        llm.complete.return_value = _llm_response(_eval_json())
        node = _sample_node(description="Parse JSON response")

        await evaluator.evaluate(node, "Goal", "result")

        user_msg = llm.complete.call_args[0][0][1]["content"]
        assert "Parse JSON response" in user_msg

    @pytest.mark.asyncio
    async def test_result_in_user_message(
        self, llm: AsyncMock, evaluator: LLMResultEvaluator
    ) -> None:
        llm.complete.return_value = _llm_response(_eval_json())
        node = _sample_node()

        await evaluator.evaluate(node, "Goal", "The API returned 200 OK with data")

        user_msg = llm.complete.call_args[0][0][1]["content"]
        assert "The API returned 200 OK with data" in user_msg

    @pytest.mark.asyncio
    async def test_system_prompt_stable_prefix(
        self, llm: AsyncMock, evaluator: LLMResultEvaluator
    ) -> None:
        """System prompt should be the same across calls (KV-cache friendly)."""
        llm.complete.return_value = _llm_response(_eval_json())
        node1 = _sample_node(description="Task A")
        node2 = _sample_node(description="Task B")

        await evaluator.evaluate(node1, "Goal A", "result A")
        system1 = llm.complete.call_args[0][0][0]["content"]

        await evaluator.evaluate(node2, "Goal B", "result B")
        system2 = llm.complete.call_args[0][0][0]["content"]

        assert system1 == system2

    @pytest.mark.asyncio
    async def test_long_result_truncated(
        self, llm: AsyncMock, evaluator: LLMResultEvaluator
    ) -> None:
        """Results longer than 2000 chars should be truncated in the prompt."""
        llm.complete.return_value = _llm_response(_eval_json())
        node = _sample_node()
        long_result = "x" * 5000

        await evaluator.evaluate(node, "Goal", long_result)

        user_msg = llm.complete.call_args[0][0][1]["content"]
        # Result should be truncated to 2000 chars
        assert len(user_msg) < 5000

    @pytest.mark.asyncio
    async def test_model_passed_to_llm(self, llm: AsyncMock) -> None:
        """Configured model is forwarded to LLM gateway."""
        llm.complete.return_value = _llm_response(_eval_json(), model="ollama/qwen3:8b")
        evaluator = LLMResultEvaluator(llm, model="ollama/qwen3:8b")
        node = _sample_node()

        await evaluator.evaluate(node, "Goal", "result")

        _, kwargs = llm.complete.call_args
        assert kwargs["model"] == "ollama/qwen3:8b"


# ===================================================================
# TestJsonParsing
# ===================================================================


class TestJsonParsing:
    """JSON extraction edge cases."""

    @pytest.mark.asyncio
    async def test_json_in_markdown_block(
        self, llm: AsyncMock, evaluator: LLMResultEvaluator
    ) -> None:
        md_json = (
            "```json\n"
            '{"accuracy": 0.9, "validity": 0.8, "goal_alignment": 0.95, "feedback": "ok"}'
            "\n```"
        )
        llm.complete.return_value = _llm_response(md_json)
        node = _sample_node()

        result = await evaluator.evaluate(node, "Goal", "result")

        assert result.accuracy == pytest.approx(0.9, abs=0.01)

    @pytest.mark.asyncio
    async def test_json_with_think_tags(
        self, llm: AsyncMock, evaluator: LLMResultEvaluator
    ) -> None:
        content = (
            "<think>analyzing result carefully</think>\n"
            '{"accuracy": 0.7, "validity": 0.6, "goal_alignment": 0.8, '
            '"feedback": "decent"}'
        )
        llm.complete.return_value = _llm_response(content)
        node = _sample_node()

        result = await evaluator.evaluate(node, "Goal", "result")

        assert result.accuracy == pytest.approx(0.7, abs=0.01)

    @pytest.mark.asyncio
    async def test_json_with_surrounding_text(
        self, llm: AsyncMock, evaluator: LLMResultEvaluator
    ) -> None:
        content = (
            "Here is my evaluation:\n"
            '{"accuracy": 0.85, "validity": 0.9, "goal_alignment": 0.75, "feedback": "solid"}\n'
            "Hope this helps!"
        )
        llm.complete.return_value = _llm_response(content)
        node = _sample_node()

        result = await evaluator.evaluate(node, "Goal", "result")

        assert result.accuracy == pytest.approx(0.85, abs=0.01)


# ===================================================================
# TestHelpers — module-level helpers
# ===================================================================


class TestHelpers:
    """Unit tests for helper functions."""

    def test_clamp_within_range(self) -> None:
        assert _clamp(0.5) == 0.5

    def test_clamp_above_max(self) -> None:
        assert _clamp(1.5) == 1.0

    def test_clamp_below_min(self) -> None:
        assert _clamp(-0.3) == 0.0

    def test_extract_json_object_plain(self) -> None:
        data = _extract_json_object('{"accuracy": 0.9, "validity": 0.8}')
        assert data["accuracy"] == 0.9

    def test_extract_json_object_with_think_tags(self) -> None:
        data = _extract_json_object('<think>thinking</think>{"accuracy": 0.7, "validity": 0.6}')
        assert data["accuracy"] == 0.7

    def test_extract_json_object_markdown_block(self) -> None:
        data = _extract_json_object('```json\n{"accuracy": 0.8}\n```')
        assert data["accuracy"] == 0.8

    def test_extract_json_object_invalid_raises(self) -> None:
        with pytest.raises((json.JSONDecodeError, ValueError)):
            _extract_json_object("no json here")
