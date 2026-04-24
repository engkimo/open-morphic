"""Tests for FractalBypassClassifier — LLM-powered intent analysis for SIMPLE bypass.

TD-167: All classification goes through LLM intent analysis.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from domain.entities.fractal_engine import (
    CandidateNode,
    PlanEvaluation,
    PlanNode,
    ResultEvaluation,
)
from domain.entities.task import SubTask, TaskEntity
from domain.ports.llm_gateway import LLMResponse
from domain.value_objects.fractal_engine import (
    NodeState,
    PlanEvalDecision,
    ResultEvalDecision,
)
from domain.value_objects.output_requirement import OutputRequirement
from domain.value_objects.status import SubTaskStatus, TaskStatus
from domain.value_objects.task_complexity import TaskComplexity
from infrastructure.fractal.bypass_classifier import (
    BypassDecision,
    FractalBypassClassifier,
)
from infrastructure.fractal.fractal_engine import FractalTaskEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _llm_response(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="test-model",
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=0.0,
    )


def _mock_llm(response_content: str) -> AsyncMock:
    llm = AsyncMock()
    llm.complete.return_value = _llm_response(response_content)
    return llm


# ---------------------------------------------------------------------------
# LLM intent analysis
# ---------------------------------------------------------------------------


class TestLLMClassification:
    """Tests for LLM-powered intent analysis."""

    @pytest.mark.asyncio
    async def test_llm_says_simple(self) -> None:
        llm = _mock_llm(json.dumps({"complexity": "SIMPLE", "reason": "Direct math"}))
        classifier = FractalBypassClassifier(llm=llm)
        decision = await classifier.should_bypass("What is 2+2?")
        assert decision.bypass is True
        assert decision.complexity == TaskComplexity.SIMPLE
        assert "math" in decision.reason.lower()
        llm.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_says_medium(self) -> None:
        resp = {"complexity": "MEDIUM", "reason": "Needs testing"}
        llm = _mock_llm(json.dumps(resp))
        classifier = FractalBypassClassifier(llm=llm)
        decision = await classifier.should_bypass("Fix the login bug with tests")
        assert decision.bypass is False
        assert decision.complexity == TaskComplexity.MEDIUM
        llm.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_says_complex(self) -> None:
        resp = {"complexity": "COMPLEX", "reason": "Multi-step"}
        llm = _mock_llm(json.dumps(resp))
        classifier = FractalBypassClassifier(llm=llm)
        decision = await classifier.should_bypass("Design a microservice architecture")
        assert decision.bypass is False
        assert decision.complexity == TaskComplexity.COMPLEX
        llm.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_with_think_tags(self) -> None:
        """qwen3:8b wraps responses in <think> tags."""
        content = (
            '<think>Let me analyze...</think>'
            '{"complexity": "SIMPLE", "reason": "trivial"}'
        )
        llm = _mock_llm(content)
        classifier = FractalBypassClassifier(llm=llm)
        decision = await classifier.should_bypass("Hello world in Python")
        assert decision.bypass is True

    @pytest.mark.asyncio
    async def test_llm_with_markdown_code_block(self) -> None:
        content = (
            '```json\n'
            '{"complexity": "SIMPLE", "reason": "single function"}\n'
            '```'
        )
        llm = _mock_llm(content)
        classifier = FractalBypassClassifier(llm=llm)
        decision = await classifier.should_bypass("Write a fibonacci function")
        assert decision.bypass is True

    @pytest.mark.asyncio
    async def test_llm_failure_defaults_to_no_bypass(self) -> None:
        llm = AsyncMock()
        llm.complete.side_effect = RuntimeError("LLM unavailable")
        classifier = FractalBypassClassifier(llm=llm)
        decision = await classifier.should_bypass("What is 2+2?")
        assert decision.bypass is False
        assert decision.complexity == TaskComplexity.MEDIUM

    @pytest.mark.asyncio
    async def test_unparseable_response_defaults_to_no_bypass(self) -> None:
        llm = _mock_llm("I think this is SIMPLE but let me think more...")
        classifier = FractalBypassClassifier(llm=llm)
        decision = await classifier.should_bypass("What is 2+2?")
        assert decision.bypass is False

    @pytest.mark.asyncio
    async def test_case_insensitive_complexity(self) -> None:
        llm = _mock_llm(json.dumps({"complexity": "simple", "reason": "easy"}))
        classifier = FractalBypassClassifier(llm=llm)
        decision = await classifier.should_bypass("Tell me a joke")
        assert decision.bypass is True

    @pytest.mark.asyncio
    async def test_unknown_complexity_defaults_to_medium(self) -> None:
        resp = {"complexity": "TRIVIAL", "reason": "new level"}
        llm = _mock_llm(json.dumps(resp))
        classifier = FractalBypassClassifier(llm=llm)
        decision = await classifier.should_bypass("something")
        assert decision.bypass is False

    @pytest.mark.asyncio
    async def test_complex_goal_analyzed_by_llm(self) -> None:
        """Even complex-looking goals go through LLM for nuanced analysis."""
        resp = {"complexity": "COMPLEX", "reason": "Architecture overhaul"}
        llm = _mock_llm(json.dumps(resp))
        classifier = FractalBypassClassifier(llm=llm)
        decision = await classifier.should_bypass(
            "Refactor the entire authentication system"
        )
        assert decision.bypass is False
        assert decision.complexity == TaskComplexity.COMPLEX
        # LLM IS called (no rule-based shortcut)
        llm.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_ambiguous_short_goal(self) -> None:
        """Short but ambiguous goals need LLM to decide."""
        resp = {"complexity": "MEDIUM", "reason": "Bug fix needs investigation"}
        llm = _mock_llm(json.dumps(resp))
        classifier = FractalBypassClassifier(llm=llm)
        decision = await classifier.should_bypass("Fix the bug")
        assert decision.bypass is False
        llm.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_model_param_forwarded(self) -> None:
        """Custom model parameter should be passed to LLM call."""
        llm = _mock_llm(json.dumps({"complexity": "SIMPLE", "reason": "ok"}))
        classifier = FractalBypassClassifier(llm=llm, model="custom-model")
        await classifier.should_bypass("test")
        call_kwargs = llm.complete.call_args
        assert call_kwargs.kwargs.get("model") == "custom-model"

    @pytest.mark.asyncio
    async def test_low_temperature_used(self) -> None:
        """Classification should use low temperature for determinism."""
        llm = _mock_llm(json.dumps({"complexity": "SIMPLE", "reason": "ok"}))
        classifier = FractalBypassClassifier(llm=llm)
        await classifier.should_bypass("test")
        call_kwargs = llm.complete.call_args
        assert call_kwargs.kwargs.get("temperature") == 0.1


# ---------------------------------------------------------------------------
# FractalTaskEngine bypass integration
# ---------------------------------------------------------------------------


def _make_fractal_mocks(*, classifier_bypass: bool = True):
    """Create common mocks for FractalTaskEngine bypass tests."""
    # Mock classifier
    classifier = AsyncMock()
    classifier.should_bypass.return_value = BypassDecision(
        bypass=classifier_bypass,
        complexity=(
            TaskComplexity.SIMPLE if classifier_bypass else TaskComplexity.MEDIUM
        ),
        reason="test",
    )

    # Mock planner + evaluators (for fractal path)
    node = PlanNode(
        id="n1", description="step", is_terminal=True, nesting_level=0,
    )
    candidate = CandidateNode(node=node, state=NodeState.VISIBLE, score=0.9)
    planner = AsyncMock()
    planner.generate_candidates.return_value = [candidate]

    plan_eval = PlanEvaluation(
        plan_id="p1", evaluator_model="test",
        completeness=0.9, feasibility=0.9, safety=1.0,
        overall_score=0.9, decision=PlanEvalDecision.APPROVED, feedback="OK",
    )
    plan_evaluator = AsyncMock()
    plan_evaluator.evaluate.return_value = plan_eval

    result_eval = ResultEvaluation(
        node_id="n1", decision=ResultEvalDecision.OK,
        feedback="Good", overall_score=0.9,
    )
    result_evaluator = AsyncMock()
    result_evaluator.evaluate.return_value = result_eval

    # Mock inner engine
    inner = AsyncMock()
    result_task = TaskEntity(goal="sub", status=TaskStatus.SUCCESS)
    result_task.subtasks = [SubTask(
        id="n1", description="step",
        status=SubTaskStatus.SUCCESS, result="Done",
    )]
    inner.execute.return_value = result_task

    return classifier, planner, plan_evaluator, result_evaluator, inner


class TestFractalEngineBypass:
    """Test that FractalTaskEngine correctly uses the bypass classifier."""

    @pytest.mark.asyncio
    async def test_simple_bypass_delegates_to_inner(self) -> None:
        """When classifier says SIMPLE, inner engine executes directly."""
        classifier, planner, pe, re_, inner = _make_fractal_mocks(
            classifier_bypass=True,
        )
        engine = FractalTaskEngine(
            planner=planner, plan_evaluator=pe, result_evaluator=re_,
            inner_engine=inner, bypass_classifier=classifier,
        )

        task = TaskEntity(goal="What is 2+2?")
        result = await engine.execute(task)

        classifier.should_bypass.assert_called_once_with("What is 2+2?")
        inner.execute.assert_called_once()
        assert result.status == TaskStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_medium_proceeds_to_fractal(self) -> None:
        """When classifier says MEDIUM, fractal planning proceeds."""
        classifier, planner, pe, re_, inner = _make_fractal_mocks(
            classifier_bypass=False,
        )
        engine = FractalTaskEngine(
            planner=planner, plan_evaluator=pe, result_evaluator=re_,
            inner_engine=inner, bypass_classifier=classifier,
        )

        task = TaskEntity(goal="Build a feature with tests")
        await engine.execute(task)

        classifier.should_bypass.assert_called_once()
        planner.generate_candidates.assert_called_once()

    @pytest.mark.asyncio
    async def test_bypass_without_classifier(self) -> None:
        """When no classifier is configured, fractal proceeds normally."""
        _, planner, pe, re_, inner = _make_fractal_mocks()
        engine = FractalTaskEngine(
            planner=planner, plan_evaluator=pe, result_evaluator=re_,
            inner_engine=inner,
            # No bypass_classifier
        )

        task = TaskEntity(goal="What is 2+2?")
        await engine.execute(task)

        planner.generate_candidates.assert_called_once()

    @pytest.mark.asyncio
    async def test_bypass_sets_simple_complexity(self) -> None:
        """Bypass path should create SubTask with SIMPLE complexity."""
        inner = AsyncMock()

        def capture_task(task):
            assert len(task.subtasks) == 1
            assert task.subtasks[0].complexity == TaskComplexity.SIMPLE
            task.status = TaskStatus.SUCCESS
            return task

        inner.execute.side_effect = capture_task

        classifier = AsyncMock()
        classifier.should_bypass.return_value = BypassDecision(
            bypass=True, complexity=TaskComplexity.SIMPLE, reason="trivial",
        )

        engine = FractalTaskEngine(
            planner=AsyncMock(), plan_evaluator=AsyncMock(),
            result_evaluator=AsyncMock(), inner_engine=inner,
            bypass_classifier=classifier,
        )

        task = TaskEntity(goal="What is 2+2?")
        await engine.execute(task)
        inner.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_bypass_classifier_error_falls_through(self) -> None:
        """If classifier raises, fall through to fractal planning."""
        _, planner, pe, re_, inner = _make_fractal_mocks()

        classifier = AsyncMock()
        classifier.should_bypass.side_effect = RuntimeError("crashed")

        engine = FractalTaskEngine(
            planner=planner, plan_evaluator=pe, result_evaluator=re_,
            inner_engine=inner, bypass_classifier=classifier,
        )

        task = TaskEntity(goal="What is 2+2?")
        await engine.execute(task)

        planner.generate_candidates.assert_called_once()


# ---------------------------------------------------------------------------
# TD-191: Output-requirement gate on bypass (Round 19 architectural fix)
# ---------------------------------------------------------------------------


def _output_classifier(requirement: OutputRequirement) -> AsyncMock:
    """Mock OutputRequirementClassifier returning a fixed requirement."""
    cls = AsyncMock()
    cls.classify.return_value = requirement
    return cls


class TestBypassOutputGate:
    """When OutputRequirementClassifier reports a non-TEXT requirement, the
    bypass path MUST be skipped — even if the bypass LLM said SIMPLE.

    Round 19 (2026-04-13): bypass misclassified a slide-creation goal as
    SIMPLE → no slide was ever produced. TD-191 closes the gap by requiring
    output_requirement == TEXT for bypass to fire."""

    @pytest.mark.asyncio
    async def test_file_artifact_blocks_bypass(self) -> None:
        """FILE_ARTIFACT goals must take the fractal path even if bypass=True."""
        classifier, planner, pe, re_, inner = _make_fractal_mocks(
            classifier_bypass=True,
        )
        engine = FractalTaskEngine(
            planner=planner, plan_evaluator=pe, result_evaluator=re_,
            inner_engine=inner, bypass_classifier=classifier,
            output_classifier=_output_classifier(OutputRequirement.FILE_ARTIFACT),
        )

        task = TaskEntity(goal="氷川神社のスライドを作って")
        await engine.execute(task)

        # Bypass path was rejected → fractal planner ran
        planner.generate_candidates.assert_called_once()

    @pytest.mark.asyncio
    async def test_code_artifact_blocks_bypass(self) -> None:
        classifier, planner, pe, re_, inner = _make_fractal_mocks(
            classifier_bypass=True,
        )
        engine = FractalTaskEngine(
            planner=planner, plan_evaluator=pe, result_evaluator=re_,
            inner_engine=inner, bypass_classifier=classifier,
            output_classifier=_output_classifier(OutputRequirement.CODE_ARTIFACT),
        )
        task = TaskEntity(goal="Write hello.py and save it")
        await engine.execute(task)
        planner.generate_candidates.assert_called_once()

    @pytest.mark.asyncio
    async def test_data_artifact_blocks_bypass(self) -> None:
        classifier, planner, pe, re_, inner = _make_fractal_mocks(
            classifier_bypass=True,
        )
        engine = FractalTaskEngine(
            planner=planner, plan_evaluator=pe, result_evaluator=re_,
            inner_engine=inner, bypass_classifier=classifier,
            output_classifier=_output_classifier(OutputRequirement.DATA_ARTIFACT),
        )
        task = TaskEntity(goal="Fetch the latest stock prices")
        await engine.execute(task)
        planner.generate_candidates.assert_called_once()

    @pytest.mark.asyncio
    async def test_text_requirement_allows_bypass(self) -> None:
        """TEXT goals may still bypass — preserves TD-167 latency win."""
        classifier, planner, pe, re_, inner = _make_fractal_mocks(
            classifier_bypass=True,
        )
        engine = FractalTaskEngine(
            planner=planner, plan_evaluator=pe, result_evaluator=re_,
            inner_engine=inner, bypass_classifier=classifier,
            output_classifier=_output_classifier(OutputRequirement.TEXT),
        )
        task = TaskEntity(goal="What is 2+2?")
        await engine.execute(task)

        # Bypass fired → inner engine called, fractal planner NOT
        inner.execute.assert_called_once()
        planner.generate_candidates.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_output_classifier_preserves_legacy_bypass(self) -> None:
        """When output_classifier is not wired, bypass behaves as in TD-167."""
        classifier, planner, pe, re_, inner = _make_fractal_mocks(
            classifier_bypass=True,
        )
        engine = FractalTaskEngine(
            planner=planner, plan_evaluator=pe, result_evaluator=re_,
            inner_engine=inner, bypass_classifier=classifier,
            # No output_classifier
        )
        task = TaskEntity(goal="What is 2+2?")
        await engine.execute(task)

        inner.execute.assert_called_once()
        planner.generate_candidates.assert_not_called()

    @pytest.mark.asyncio
    async def test_output_classifier_error_does_not_block_bypass(self) -> None:
        """Classifier exception must not regress to permanent fractal fallback
        for legitimate text Q&A. Fail-open is acceptable here because the
        bypass classifier has its own confidence check."""
        classifier, planner, pe, re_, inner = _make_fractal_mocks(
            classifier_bypass=True,
        )
        broken_output = AsyncMock()
        broken_output.classify.side_effect = RuntimeError("LLM down")

        engine = FractalTaskEngine(
            planner=planner, plan_evaluator=pe, result_evaluator=re_,
            inner_engine=inner, bypass_classifier=classifier,
            output_classifier=broken_output,
        )
        task = TaskEntity(goal="What is 2+2?")
        await engine.execute(task)

        # Fail-open: bypass still fires when classifier errors
        inner.execute.assert_called_once()
