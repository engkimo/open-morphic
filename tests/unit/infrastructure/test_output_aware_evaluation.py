"""Tests for Output-Aware Evaluation — Plan B (Gate ② extension).

Verifies that Gate ② prompt includes output-requirement-specific instructions
when a PlanNode has an output_requirement set.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from domain.entities.fractal_engine import PlanNode
from domain.ports.llm_gateway import LLMGateway, LLMResponse
from domain.value_objects.fractal_engine import ResultEvalDecision
from domain.value_objects.output_requirement import OutputRequirement
from infrastructure.fractal.llm_result_evaluator import LLMResultEvaluator


def _llm_response(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="test-model",
        prompt_tokens=50,
        completion_tokens=30,
        cost_usd=0.0,
    )


def _eval_json(**overrides) -> str:
    data = {
        "accuracy": 0.8,
        "validity": 0.7,
        "goal_alignment": 0.9,
        "feedback": "OK",
    }
    data.update(overrides)
    return json.dumps(data)


def _node(
    desc: str = "Create PPTX slides",
    output_req: OutputRequirement | None = None,
) -> PlanNode:
    return PlanNode(
        description=desc,
        is_terminal=True,
        output_requirement=output_req,
    )


class TestGate2OutputAwarePrompt:
    """Verify that _build_messages includes output-specific hints."""

    def test_no_hint_when_requirement_is_none(self):
        node = _node(output_req=None)
        messages = LLMResultEvaluator._build_messages(node, "Goal", "Result text")
        user_content = messages[1]["content"]
        assert "FILE ARTIFACT" not in user_content
        assert "CODE ARTIFACT" not in user_content

    def test_no_hint_when_requirement_is_text(self):
        node = _node(output_req=OutputRequirement.TEXT)
        messages = LLMResultEvaluator._build_messages(node, "Goal", "Result text")
        user_content = messages[1]["content"]
        assert "FILE ARTIFACT" not in user_content

    def test_file_artifact_hint(self):
        node = _node(output_req=OutputRequirement.FILE_ARTIFACT)
        messages = LLMResultEvaluator._build_messages(node, "Goal", "Result text")
        user_content = messages[1]["content"]
        assert "FILE ARTIFACT" in user_content
        assert "fs_write" in user_content
        assert "goal_alignment should be LOW" in user_content

    def test_code_artifact_hint(self):
        node = _node(output_req=OutputRequirement.CODE_ARTIFACT)
        messages = LLMResultEvaluator._build_messages(node, "Goal", "Result text")
        user_content = messages[1]["content"]
        assert "CODE ARTIFACT" in user_content
        assert "goal_alignment should be LOW" in user_content

    def test_data_artifact_hint(self):
        node = _node(output_req=OutputRequirement.DATA_ARTIFACT)
        messages = LLMResultEvaluator._build_messages(node, "Goal", "Result text")
        user_content = messages[1]["content"]
        assert "DATA retrieval" in user_content
        assert "goal_alignment should be LOW" in user_content


class TestGate2EvaluationWithOutputRequirement:
    """E2E: verify evaluate() works with output_requirement set."""

    @pytest.fixture
    def llm(self) -> AsyncMock:
        return AsyncMock(spec=LLMGateway)

    @pytest.fixture
    def evaluator(self, llm: AsyncMock) -> LLMResultEvaluator:
        return LLMResultEvaluator(llm=llm)

    async def test_evaluate_file_node_high_score(self, evaluator, llm):
        """Gate ② with FILE_ARTIFACT requirement: LLM returns high score → OK."""
        llm.complete.return_value = _llm_response(_eval_json(goal_alignment=0.9))
        node = _node(output_req=OutputRequirement.FILE_ARTIFACT)
        result = await evaluator.evaluate(node, "Create slides", "Created slides.pptx")
        assert result.decision == ResultEvalDecision.OK

    async def test_evaluate_file_node_low_alignment(self, evaluator, llm):
        """Gate ② with FILE_ARTIFACT: low goal_alignment → RETRY or REPLAN."""
        llm.complete.return_value = _llm_response(
            _eval_json(goal_alignment=0.2, accuracy=0.3, validity=0.3)
        )
        node = _node(output_req=OutputRequirement.FILE_ARTIFACT)
        result = await evaluator.evaluate(node, "Create slides", "Text about slides")
        # Low scores across the board → should not be OK
        assert result.decision != ResultEvalDecision.OK

    async def test_system_prompt_unchanged(self, evaluator, llm):
        """System prompt is stable (KV-cache friendly). Output hints go in user msg."""
        llm.complete.return_value = _llm_response(_eval_json())
        node = _node(output_req=OutputRequirement.FILE_ARTIFACT)
        await evaluator.evaluate(node, "Goal", "Result")
        messages = llm.complete.call_args.args[0]
        system_content = messages[0]["content"]
        # System prompt should NOT contain output hints — those go in user message
        assert "FILE ARTIFACT" not in system_content
