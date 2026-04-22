"""Tests for LLMPlanEvaluator — fractal engine Gate ① implementation.

Sprint 15.3: ~12 tests covering single/multi-model evaluation, JSON parsing,
fallback behavior, prompt construction, and aggregation integration.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from domain.entities.fractal_engine import (
    CandidateNode,
    ExecutionPlan,
    PlanEvaluation,
    PlanNode,
)
from domain.ports.llm_gateway import LLMGateway, LLMResponse
from domain.value_objects.fractal_engine import NodeState, PlanEvalDecision
from domain.value_objects.status import PlanStatus
from infrastructure.fractal.llm_plan_evaluator import LLMPlanEvaluator

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
    completeness: float = 0.8,
    feasibility: float = 0.7,
    safety: float = 1.0,
    feedback: str = "Plan looks solid",
) -> str:
    return json.dumps(
        {
            "completeness": completeness,
            "feasibility": feasibility,
            "safety": safety,
            "feedback": feedback,
        }
    )


def _sample_plan(
    goal: str = "Build a REST API",
    node_count: int = 3,
) -> ExecutionPlan:
    nodes = [
        PlanNode(
            description=f"Step {i + 1}: action {i + 1}",
            nesting_level=0,
            is_terminal=i == node_count - 1,
        )
        for i in range(node_count)
    ]
    conditional = CandidateNode(
        node=PlanNode(description="Fallback step", nesting_level=0, is_terminal=True),
        state=NodeState.CONDITIONAL,
        activation_condition="primary step fails",
        score=0.4,
    )
    return ExecutionPlan(
        goal=goal,
        visible_nodes=nodes,
        candidate_space=[conditional],
        status=PlanStatus.PROPOSED,
    )


@pytest.fixture
def llm() -> AsyncMock:
    return AsyncMock(spec=LLMGateway)


@pytest.fixture
def evaluator(llm: AsyncMock) -> LLMPlanEvaluator:
    return LLMPlanEvaluator(llm, min_score=0.5)


# ===================================================================
# TestSingleModelEvaluation
# ===================================================================


class TestSingleModelEvaluation:
    """Evaluation with a single (default) model."""

    @pytest.mark.asyncio
    async def test_evaluates_plan_with_default_model(
        self, llm: AsyncMock, evaluator: LLMPlanEvaluator
    ) -> None:
        llm.complete.return_value = _llm_response(_eval_json(0.8, 0.7, 1.0))
        plan = _sample_plan()

        result = await evaluator.evaluate(plan, "Build a REST API")

        assert isinstance(result, PlanEvaluation)
        assert result.completeness == pytest.approx(0.8, abs=0.01)
        assert result.feasibility == pytest.approx(0.7, abs=0.01)
        assert result.safety == pytest.approx(1.0, abs=0.01)
        assert result.decision == PlanEvalDecision.APPROVED

    @pytest.mark.asyncio
    async def test_low_scores_rejected(self, llm: AsyncMock, evaluator: LLMPlanEvaluator) -> None:
        llm.complete.return_value = _llm_response(_eval_json(0.2, 0.3, 0.4))
        plan = _sample_plan()

        result = await evaluator.evaluate(plan, "Complex goal")

        assert result.decision == PlanEvalDecision.REJECTED

    @pytest.mark.asyncio
    async def test_plan_id_preserved(self, llm: AsyncMock, evaluator: LLMPlanEvaluator) -> None:
        llm.complete.return_value = _llm_response(_eval_json())
        plan = _sample_plan()

        result = await evaluator.evaluate(plan, "Goal")

        assert result.plan_id == plan.id

    @pytest.mark.asyncio
    async def test_scores_clamped_to_valid_range(
        self, llm: AsyncMock, evaluator: LLMPlanEvaluator
    ) -> None:
        payload = json.dumps(
            {"completeness": 1.5, "feasibility": -0.3, "safety": 0.8, "feedback": ""}
        )
        llm.complete.return_value = _llm_response(payload)
        plan = _sample_plan()

        result = await evaluator.evaluate(plan, "Goal")

        assert result.completeness == pytest.approx(1.0, abs=0.01)
        assert result.feasibility == pytest.approx(0.0, abs=0.01)


# ===================================================================
# TestMultiModelEvaluation
# ===================================================================


class TestMultiModelEvaluation:
    """Evaluation with multiple configured models."""

    @pytest.mark.asyncio
    async def test_multiple_models_evaluated_and_aggregated(self, llm: AsyncMock) -> None:
        # Two models return different scores
        llm.complete.side_effect = [
            _llm_response(_eval_json(0.8, 0.6, 1.0), model="ollama/qwen3:8b"),
            _llm_response(_eval_json(0.6, 0.8, 0.8), model="claude-sonnet"),
        ]
        evaluator = LLMPlanEvaluator(
            llm,
            models=["ollama/qwen3:8b", "claude-sonnet"],
            min_score=0.5,
        )
        plan = _sample_plan()

        result = await evaluator.evaluate(plan, "Build a REST API")

        assert result.completeness == pytest.approx(0.7, abs=0.01)
        assert result.feasibility == pytest.approx(0.7, abs=0.01)
        assert result.safety == pytest.approx(0.9, abs=0.01)
        assert "aggregated(2)" in result.evaluator_model
        assert result.decision == PlanEvalDecision.APPROVED

    @pytest.mark.asyncio
    async def test_three_models_with_one_low(self, llm: AsyncMock) -> None:
        llm.complete.side_effect = [
            _llm_response(_eval_json(0.9, 0.9, 0.9), model="model-a"),
            _llm_response(_eval_json(0.8, 0.8, 0.8), model="model-b"),
            _llm_response(_eval_json(0.1, 0.1, 0.1), model="model-c"),
        ]
        evaluator = LLMPlanEvaluator(
            llm,
            models=["model-a", "model-b", "model-c"],
            min_score=0.5,
        )
        plan = _sample_plan()

        result = await evaluator.evaluate(plan, "Goal")

        assert result.decision == PlanEvalDecision.APPROVED
        assert llm.complete.call_count == 3

    @pytest.mark.asyncio
    async def test_empty_models_uses_default(
        self, llm: AsyncMock, evaluator: LLMPlanEvaluator
    ) -> None:
        llm.complete.return_value = _llm_response(_eval_json())
        plan = _sample_plan()

        await evaluator.evaluate(plan, "Goal")

        _, kwargs = llm.complete.call_args
        assert kwargs["model"] is None


# ===================================================================
# TestFallback
# ===================================================================


class TestFallback:
    """Fallback behavior on LLM failure or bad output."""

    @pytest.mark.asyncio
    async def test_invalid_json_returns_fallback(
        self, llm: AsyncMock, evaluator: LLMPlanEvaluator
    ) -> None:
        llm.complete.return_value = _llm_response("Not valid JSON at all!!!")
        plan = _sample_plan()

        result = await evaluator.evaluate(plan, "Goal")

        assert result.completeness == pytest.approx(0.5, abs=0.01)
        assert result.feasibility == pytest.approx(0.5, abs=0.01)
        assert result.safety == pytest.approx(1.0, abs=0.01)
        assert "Fallback" in result.feedback

    @pytest.mark.asyncio
    async def test_llm_exception_returns_fallback(
        self, llm: AsyncMock, evaluator: LLMPlanEvaluator
    ) -> None:
        llm.complete.side_effect = RuntimeError("LLM unavailable")
        plan = _sample_plan()

        result = await evaluator.evaluate(plan, "Goal")

        assert result.completeness == pytest.approx(0.5, abs=0.01)
        assert "Fallback" in result.feedback

    @pytest.mark.asyncio
    async def test_partial_model_failure_still_aggregates(self, llm: AsyncMock) -> None:
        """One model fails, one succeeds → aggregation of fallback + real."""
        llm.complete.side_effect = [
            _llm_response(_eval_json(0.9, 0.9, 0.9), model="good-model"),
            RuntimeError("Model B unavailable"),
        ]
        evaluator = LLMPlanEvaluator(llm, models=["good-model", "bad-model"], min_score=0.5)
        plan = _sample_plan()

        result = await evaluator.evaluate(plan, "Goal")

        # Average of real (0.9,0.9,0.9) + fallback (0.5,0.5,1.0)
        assert result.completeness == pytest.approx(0.7, abs=0.01)
        assert result.decision == PlanEvalDecision.APPROVED


# ===================================================================
# TestPromptConstruction
# ===================================================================


class TestPromptConstruction:
    """Verify prompt content passed to the LLM gateway."""

    @pytest.mark.asyncio
    async def test_goal_in_user_message(self, llm: AsyncMock, evaluator: LLMPlanEvaluator) -> None:
        llm.complete.return_value = _llm_response(_eval_json())
        plan = _sample_plan(goal="Deploy microservices")

        await evaluator.evaluate(plan, "Deploy microservices")

        messages = llm.complete.call_args[0][0]
        assert "Deploy microservices" in messages[1]["content"]

    @pytest.mark.asyncio
    async def test_plan_nodes_in_user_message(
        self, llm: AsyncMock, evaluator: LLMPlanEvaluator
    ) -> None:
        llm.complete.return_value = _llm_response(_eval_json())
        plan = _sample_plan(node_count=2)

        await evaluator.evaluate(plan, "Goal")

        messages = llm.complete.call_args[0][0]
        user_msg = messages[1]["content"]
        assert "Step 1" in user_msg
        assert "Step 2" in user_msg

    @pytest.mark.asyncio
    async def test_system_prompt_stable_prefix(
        self, llm: AsyncMock, evaluator: LLMPlanEvaluator
    ) -> None:
        """System prompt should be the same across calls (KV-cache friendly)."""
        llm.complete.return_value = _llm_response(_eval_json())
        plan1 = _sample_plan(goal="Goal A")
        plan2 = _sample_plan(goal="Goal B")

        await evaluator.evaluate(plan1, "Goal A")
        system1 = llm.complete.call_args[0][0][0]["content"]

        await evaluator.evaluate(plan2, "Goal B")
        system2 = llm.complete.call_args[0][0][0]["content"]

        assert system1 == system2

    @pytest.mark.asyncio
    async def test_conditional_nodes_in_prompt(
        self, llm: AsyncMock, evaluator: LLMPlanEvaluator
    ) -> None:
        llm.complete.return_value = _llm_response(_eval_json())
        plan = _sample_plan()

        await evaluator.evaluate(plan, "Goal")

        user_msg = llm.complete.call_args[0][0][1]["content"]
        assert "Fallback step" in user_msg
        assert "primary step fails" in user_msg


# ===================================================================
# TestJsonParsing
# ===================================================================


class TestJsonParsing:
    """JSON extraction edge cases."""

    @pytest.mark.asyncio
    async def test_json_in_markdown_block(
        self, llm: AsyncMock, evaluator: LLMPlanEvaluator
    ) -> None:
        md_json = (
            "```json\n"
            '{"completeness": 0.9, "feasibility": 0.8, "safety": 0.95, "feedback": "ok"}'
            "\n```"
        )
        llm.complete.return_value = _llm_response(md_json)
        plan = _sample_plan()

        result = await evaluator.evaluate(plan, "Goal")

        assert result.completeness == pytest.approx(0.9, abs=0.01)

    @pytest.mark.asyncio
    async def test_json_with_think_tags(self, llm: AsyncMock, evaluator: LLMPlanEvaluator) -> None:
        content = (
            "<think>analyzing plan</think>\n"
            '{"completeness": 0.7, "feasibility": 0.6, "safety": 0.9, '
            '"feedback": "decent"}'
        )
        llm.complete.return_value = _llm_response(content)
        plan = _sample_plan()

        result = await evaluator.evaluate(plan, "Goal")

        assert result.completeness == pytest.approx(0.7, abs=0.01)
