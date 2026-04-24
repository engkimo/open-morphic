"""Live regression test for Round 19 (TD-191).

Round 19 (2026-04-13) reproduced a class of failure: a slide-creation goal
("氷川神社のスライドを作って") was misclassified as SIMPLE by the bypass
classifier, the engine delegated to the inner LangGraph runtime, and 300+
seconds later the hard timeout (TD-181) triggered with no slide produced.

TD-191 hoisted ``OutputRequirementClassifier`` above the bypass block so
non-text goals always take the fractal path. This test exercises the fix
end-to-end with a real Ollama LLM ($0) so the architectural guard is
verified against actual model behavior, not just mocked decisions.

Run with: ``uv run pytest tests/integration/test_round19_regression.py -v -s``
Requires: Ollama running with qwen3:8b (or qwen3-coder).
"""

from __future__ import annotations

import asyncio
import shutil
from unittest.mock import AsyncMock

import pytest

from domain.entities.fractal_engine import (
    CandidateNode,
    PlanEvaluation,
    PlanNode,
    ResultEvaluation,
)
from domain.entities.task import SubTask, TaskEntity
from domain.services.output_requirement_classifier import OutputRequirementClassifier
from domain.value_objects.fractal_engine import (
    NodeState,
    PlanEvalDecision,
    ResultEvalDecision,
)
from domain.value_objects.output_requirement import OutputRequirement
from domain.value_objects.status import SubTaskStatus, TaskStatus
from infrastructure.fractal.bypass_classifier import FractalBypassClassifier
from infrastructure.fractal.fractal_engine import FractalTaskEngine
from infrastructure.llm.cost_tracker import CostTracker
from infrastructure.llm.litellm_gateway import LiteLLMGateway
from infrastructure.llm.ollama_manager import OllamaManager
from shared.config import Settings

_HAS_OLLAMA = shutil.which("ollama") is not None

pytestmark = [
    pytest.mark.ollama,
    pytest.mark.skipif(not _HAS_OLLAMA, reason="Ollama CLI not installed"),
]

# Round 19 reproducer — DO NOT change without re-validating the architectural guard.
ROUND_19_GOAL = "氷川神社のスライドを作って"

# Other artifact-producing goals expected to escape the bypass.
ARTIFACT_GOALS = [
    ROUND_19_GOAL,
    "Create a one-page PDF report on quantum computing",
    "Generate an Excel spreadsheet of monthly expenses",
]


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


class _InMemoryCostRepo:
    """Minimal CostRepository — integration tests don't persist."""

    def __init__(self) -> None:
        self._records: list = []

    async def save(self, record) -> None:
        self._records.append(record)

    async def get_daily_total(self) -> float:
        return sum(r.cost_usd for r in self._records)

    async def get_monthly_total(self) -> float:
        return sum(r.cost_usd for r in self._records)

    async def get_local_usage_rate(self) -> float:
        if not self._records:
            return 0.0
        local = sum(1 for r in self._records if r.is_local)
        return local / len(self._records)


@pytest.fixture(scope="module")
async def ollama() -> OllamaManager:
    mgr = OllamaManager()
    if not await mgr.is_running():
        pytest.skip("Ollama not running")
    models = await mgr.list_models()
    if not any("qwen3" in m for m in models):
        pytest.skip("qwen3 model not available")
    return mgr


@pytest.fixture(scope="module")
async def gateway(ollama: OllamaManager) -> LiteLLMGateway:
    settings = Settings()
    cost_tracker = CostTracker(_InMemoryCostRepo())
    return LiteLLMGateway(ollama=ollama, cost_tracker=cost_tracker, settings=settings)


@pytest.fixture(scope="module")
def output_classifier(gateway: LiteLLMGateway) -> OutputRequirementClassifier:
    return OutputRequirementClassifier(llm=gateway)


@pytest.fixture(scope="module")
def bypass_classifier(gateway: LiteLLMGateway) -> FractalBypassClassifier:
    return FractalBypassClassifier(llm=gateway)


# ══════════════════════════════════════════════════════════
# Layer 1: real LLM classifies Round 19 goal as non-TEXT
# ══════════════════════════════════════════════════════════


class TestOutputClassificationIsCorrect:
    """The whole TD-191 fix rests on OutputRequirementClassifier returning
    something other than TEXT for artifact-producing goals. If the LLM
    misjudges this, the gate fails open and Round 19 returns."""

    @pytest.mark.parametrize("goal", ARTIFACT_GOALS)
    async def test_artifact_goal_is_not_text(
        self, goal: str, output_classifier: OutputRequirementClassifier
    ) -> None:
        requirement = await output_classifier.classify(goal)
        print(f"\n  goal={goal!r}\n  → requirement={requirement.value}")
        assert requirement != OutputRequirement.TEXT, (
            f"Output classifier returned TEXT for {goal!r} — "
            "TD-191 gate would fail-open and bypass would fire. "
            "This is the Round 19 root cause; investigate the classifier prompt."
        )

    async def test_text_question_is_text(
        self, output_classifier: OutputRequirementClassifier
    ) -> None:
        """Sanity check: pure Q&A must classify as TEXT so bypass still fires."""
        requirement = await output_classifier.classify("What is 2+2?")
        print(f"\n  goal='What is 2+2?'\n  → requirement={requirement.value}")
        assert requirement == OutputRequirement.TEXT


# ══════════════════════════════════════════════════════════
# Layer 2: end-to-end FractalTaskEngine.execute() with real classifiers
# ══════════════════════════════════════════════════════════


def _stub_planning_path():
    """Mock planner / evaluators / inner engine so the fractal path completes
    quickly. We only care that the bypass decision is correct — actual
    artifact production is a separate concern (LAEE / engine wiring)."""
    node = PlanNode(
        id="n1", description="produce artifact", is_terminal=True, nesting_level=0,
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

    inner = AsyncMock()
    result_task = TaskEntity(goal="sub", status=TaskStatus.SUCCESS)
    result_task.subtasks = [SubTask(
        id="n1", description="produce artifact",
        status=SubTaskStatus.SUCCESS, result="produced",
    )]
    inner.execute.return_value = result_task

    return planner, plan_evaluator, result_evaluator, inner


class TestRound19EndToEnd:
    """Full FractalTaskEngine.execute() with REAL bypass + output classifiers
    against REAL Ollama. Asserts TD-191 gate behavior under live conditions."""

    async def test_round19_goal_takes_fractal_path(
        self,
        bypass_classifier: FractalBypassClassifier,
        output_classifier: OutputRequirementClassifier,
    ) -> None:
        """The exact goal that broke Round 19 must NOT trigger bypass."""
        planner, pe, re_, inner = _stub_planning_path()
        engine = FractalTaskEngine(
            planner=planner, plan_evaluator=pe, result_evaluator=re_,
            inner_engine=inner,
            bypass_classifier=bypass_classifier,
            output_classifier=output_classifier,
        )

        task = TaskEntity(goal=ROUND_19_GOAL)
        await engine.execute(task)

        # The fractal planner must have been engaged, not bypass.
        planner.generate_candidates.assert_called()
        print(
            f"\n  ✓ Round 19 goal {ROUND_19_GOAL!r} took fractal path "
            f"(planner.generate_candidates called {planner.generate_candidates.call_count}x)"
        )

    async def test_simple_question_still_bypasses(
        self,
        bypass_classifier: FractalBypassClassifier,
        output_classifier: OutputRequirementClassifier,
    ) -> None:
        """TD-167's latency win for legitimate text Q&A must be preserved."""
        planner, pe, re_, inner = _stub_planning_path()
        engine = FractalTaskEngine(
            planner=planner, plan_evaluator=pe, result_evaluator=re_,
            inner_engine=inner,
            bypass_classifier=bypass_classifier,
            output_classifier=output_classifier,
        )

        task = TaskEntity(goal="What is 2+2?")
        await engine.execute(task)

        # Bypass fired → inner engine got the call, planner did not.
        inner.execute.assert_called_once()
        planner.generate_candidates.assert_not_called()
        print("\n  ✓ 'What is 2+2?' still takes bypass (TD-167 latency preserved)")
