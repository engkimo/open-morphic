"""Live integration test for the Council pilot (TD-194).

Wires real LiteLLMGateway + real TwoEngineDebate + real InMemoryEventBus +
real RunCouncilDebateUseCase, then exercises one debate between Ollama
(local, $0) and Gemini Flash (cloud judge). Skipped automatically when
the prerequisites are missing so the unit suite stays portable.

Run with: ``uv run --extra dev pytest tests/integration/test_council_pilot_live.py -v -s -m live``

Prereqs:
- ``ollama`` CLI installed and serving qwen3:8b
- ``GOOGLE_GEMINI_API_KEY`` (or ``GEMINI_API_KEY``) env var
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time

import pytest

from application.use_cases.run_council_debate import RunCouncilDebateUseCase  # noqa: E402
from domain.entities.council import SubtaskBrief
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.council_events import DebateStarted, DecisionResolved
from domain.value_objects.model_tier import TaskType
from infrastructure.council.two_engine_debate import TwoEngineDebate
from infrastructure.events.in_memory_event_bus import InMemoryEventBus
from infrastructure.llm.cost_tracker import CostTracker
from infrastructure.llm.litellm_gateway import LiteLLMGateway
from infrastructure.llm.ollama_manager import OllamaManager
from shared.config import Settings

_HAS_OLLAMA = shutil.which("ollama") is not None


def _has_gemini_key() -> bool:
    if os.environ.get("GOOGLE_GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        return True
    try:
        return bool(Settings().google_gemini_api_key)
    except Exception:
        return False


_HAS_GEMINI = _has_gemini_key()

pytestmark = [
    pytest.mark.live,
    pytest.mark.asyncio,
    pytest.mark.skipif(not _HAS_OLLAMA, reason="Ollama CLI not installed"),
    pytest.mark.skipif(not _HAS_GEMINI, reason="Gemini API key not set"),
]


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


async def test_two_engine_debate_live_ollama_vs_gemini() -> None:
    settings = Settings()
    ollama = OllamaManager()
    if not await ollama.is_running():
        pytest.skip("Ollama not running")
    models = await ollama.list_models()
    if not any("qwen3" in m for m in models):
        pytest.skip("qwen3 model not available")

    cost_repo = _InMemoryCostRepo()
    cost_tracker = CostTracker(cost_repo)
    gateway = LiteLLMGateway(
        ollama=ollama, cost_tracker=cost_tracker, settings=settings
    )

    event_bus = InMemoryEventBus()
    debate = TwoEngineDebate(
        llm_gateway=gateway,
        resolver_model=settings.council_resolver_model,
    )
    use_case = RunCouncilDebateUseCase(
        debate_port=debate, event_bus=event_bus, timeout_seconds=15.0
    )

    subtask = SubtaskBrief(
        id="live-bread-plan",
        description="Summarize a 2-paragraph plan to bake bread.",
        task_type=TaskType.SIMPLE_QA,
    )
    candidates = [AgentEngineType.OLLAMA, AgentEngineType.GEMINI_CLI]

    start_total = await cost_repo.get_daily_total()
    start = time.monotonic()
    decision = await use_case.execute(subtask, candidates)
    elapsed = time.monotonic() - start
    end_total = await cost_repo.get_daily_total()
    cost_usd = end_total - start_total

    print(
        f"\n  decision.engine={decision.agent_engine.value if decision else None}\n"
        f"  rationale={decision.rationale if decision else None!r}\n"
        f"  events={[e.kind for e in event_bus.events]}\n"
        f"  elapsed={elapsed:.2f}s cost_usd={cost_usd:.5f}"
    )

    assert decision is not None, "council debate must return a Decision live"
    assert decision.agent_engine in {
        AgentEngineType.OLLAMA,
        AgentEngineType.GEMINI_CLI,
    }
    assert decision.rationale.strip(), "rationale must be non-empty"
    rationale_lower = decision.rationale.lower()
    assert "ollama" in rationale_lower, "judge should reference ollama by name"
    assert "gemini" in rationale_lower, "judge should reference gemini by name"

    assert len(event_bus.events) >= 4, event_bus.events
    assert isinstance(event_bus.events[0], DebateStarted)
    assert isinstance(event_bus.events[-1], DecisionResolved)
    assert elapsed < 15.0, f"NFR-1 budget exceeded: {elapsed:.2f}s"
    assert cost_usd < 0.02, f"NFR cost budget exceeded: ${cost_usd:.5f}"


if __name__ == "__main__":
    asyncio.run(test_two_engine_debate_live_ollama_vs_gemini())
