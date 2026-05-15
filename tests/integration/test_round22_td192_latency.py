"""Live latency regression — TD-192 fractal-entry LLM call reduction.

Round 22 (2026-05-15) verifies that folding ``OutputRequirementClassifier``
into ``FractalBypassClassifier`` collapses the fractal-entry classification
from **two** LLM round-trips into **one**, against a real Ollama backend
($0). Pre-TD-192 baseline = 2 calls/goal (bypass classifier + output
classifier). Post-TD-192 target = 1 call/goal.

The test also re-verifies the TD-191 architectural guard end-to-end:
- Artifact goal (Round 19 reproducer) → bypass=False, output != TEXT.
- Plain text Q&A → bypass=True, output == TEXT.

Run with: ``uv run pytest tests/integration/test_round22_td192_latency.py -v -s``
Requires: Ollama running with qwen3:8b (or qwen3-coder).
"""

from __future__ import annotations

import asyncio
import shutil
import time

import pytest

from domain.ports.llm_gateway import LLMGateway, LLMResponse
from domain.value_objects.output_requirement import OutputRequirement
from domain.value_objects.task_complexity import TaskComplexity
from infrastructure.fractal.bypass_classifier import FractalBypassClassifier
from infrastructure.llm.cost_tracker import CostTracker
from infrastructure.llm.litellm_gateway import LiteLLMGateway
from infrastructure.llm.ollama_manager import OllamaManager
from shared.config import Settings

_HAS_OLLAMA = shutil.which("ollama") is not None

pytestmark = [
    pytest.mark.ollama,
    pytest.mark.skipif(not _HAS_OLLAMA, reason="Ollama CLI not installed"),
]

ROUND_19_GOAL = "氷川神社のスライドを作って"
TEXT_GOAL = "What is 2+2?"

# Pre-TD-192 baseline: bypass classifier + output classifier = 2 calls.
PRE_TD192_CALLS_PER_GOAL = 2
TARGET_CALLS_PER_GOAL = 1


class _InMemoryCostRepo:
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


class _SpyLLMGateway(LLMGateway):
    """Counts ``complete()`` invocations, delegating to a real backend."""

    def __init__(self, inner: LLMGateway) -> None:
        self._inner = inner
        self.call_count = 0

    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        self.call_count += 1
        return await self._inner.complete(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def is_available(self, model: str) -> bool:
        return await self._inner.is_available(model)

    async def list_models(self) -> list[str]:
        return await self._inner.list_models()


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


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
async def real_gateway(ollama: OllamaManager) -> LiteLLMGateway:
    return LiteLLMGateway(
        ollama=ollama,
        cost_tracker=CostTracker(_InMemoryCostRepo()),
        settings=Settings(),
    )


class TestTD192CallCountReduction:
    """Each fractal-entry classification must issue exactly one LLM call."""

    async def test_artifact_goal_uses_one_call(
        self, real_gateway: LiteLLMGateway,
    ) -> None:
        spy = _SpyLLMGateway(real_gateway)
        classifier = FractalBypassClassifier(llm=spy)

        t0 = time.perf_counter()
        decision = await classifier.should_bypass(ROUND_19_GOAL)
        elapsed = time.perf_counter() - t0

        assert spy.call_count == TARGET_CALLS_PER_GOAL, (
            f"TD-192: expected {TARGET_CALLS_PER_GOAL} LLM call for fractal-entry "
            f"classification, got {spy.call_count} (pre-TD-192 baseline = "
            f"{PRE_TD192_CALLS_PER_GOAL})"
        )
        # TD-191 guard: artifact goals must NOT bypass.
        assert decision.bypass is False, (
            f"Artifact goal {ROUND_19_GOAL!r} must take the fractal path "
            f"(decision={decision})"
        )
        assert decision.output_requirement != OutputRequirement.TEXT, (
            f"Artifact goal must classify as non-TEXT (got "
            f"{decision.output_requirement.value})"
        )
        print(
            f"\n  ✓ Round 19 goal: 1 LLM call ({elapsed:.2f}s), "
            f"bypass={decision.bypass}, output={decision.output_requirement.value}, "
            f"complexity={decision.complexity.value}"
        )

    async def test_text_goal_uses_one_call(
        self, real_gateway: LiteLLMGateway,
    ) -> None:
        spy = _SpyLLMGateway(real_gateway)
        classifier = FractalBypassClassifier(llm=spy)

        t0 = time.perf_counter()
        decision = await classifier.should_bypass(TEXT_GOAL)
        elapsed = time.perf_counter() - t0

        assert spy.call_count == TARGET_CALLS_PER_GOAL, (
            f"TD-192: expected {TARGET_CALLS_PER_GOAL} LLM call, got "
            f"{spy.call_count} (pre-TD-192 baseline = {PRE_TD192_CALLS_PER_GOAL})"
        )
        # Plain text Q&A should still bypass — TD-167 latency win preserved.
        assert decision.bypass is True, (
            f"Plain text goal {TEXT_GOAL!r} must bypass (decision={decision})"
        )
        assert decision.complexity == TaskComplexity.SIMPLE
        assert decision.output_requirement == OutputRequirement.TEXT
        print(
            f"\n  ✓ Text Q&A: 1 LLM call ({elapsed:.2f}s), bypass={decision.bypass}, "
            f"output={decision.output_requirement.value}, "
            f"complexity={decision.complexity.value}"
        )

    async def test_round22_summary(self, real_gateway: LiteLLMGateway) -> None:
        """End-to-end summary: 2 goals × 1 call = 2 total (was 4)."""
        spy = _SpyLLMGateway(real_gateway)
        classifier = FractalBypassClassifier(llm=spy)

        t0 = time.perf_counter()
        artifact = await classifier.should_bypass(ROUND_19_GOAL)
        text = await classifier.should_bypass(TEXT_GOAL)
        elapsed = time.perf_counter() - t0

        expected_total = TARGET_CALLS_PER_GOAL * 2
        baseline_total = PRE_TD192_CALLS_PER_GOAL * 2
        assert spy.call_count == expected_total
        assert artifact.bypass is False
        assert text.bypass is True

        saved = baseline_total - spy.call_count
        print(
            f"\n  ✓ Round 22 summary: {spy.call_count} LLM calls for 2 goals "
            f"(baseline {baseline_total}, saved {saved} calls, total {elapsed:.2f}s)"
        )
