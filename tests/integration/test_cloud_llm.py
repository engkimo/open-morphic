"""Cloud LLM API integration tests — real API calls to Anthropic, OpenAI, Gemini.

Run with: uv run pytest tests/integration/test_cloud_llm.py -v -s
Requires: API keys set in .env (ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_GEMINI_API_KEY)

Note: Tests skip gracefully when API keys are missing or invalid (quota exceeded,
expired key, etc.). This allows partial test runs with only the available providers.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from domain.value_objects.model_tier import TaskType
from infrastructure.llm.cost_tracker import CostTracker
from infrastructure.llm.litellm_gateway import LiteLLMGateway
from infrastructure.llm.ollama_manager import OllamaManager
from shared.config import Settings


# ── Shared helpers ──


class _InMemoryCostRepo:
    """Minimal in-memory CostRepository for integration tests."""

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


async def _try_complete(gateway: LiteLLMGateway, model: str, messages: list) -> object:
    """Attempt completion, skip test on auth/quota errors."""
    try:
        return await gateway.complete(messages=messages, model=model)
    except Exception as e:
        error_str = str(e).lower()
        if any(
            kw in error_str
            for kw in [
                "quota", "rate limit", "authentication", "invalid api key",
                "api_key_invalid", "not found", "no longer available",
            ]
        ):
            pytest.skip(f"{model}: {type(e).__name__} — {str(e)[:120]}")
        raise


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings()


@pytest.fixture(scope="module")
async def ollama() -> OllamaManager:
    return OllamaManager()


@pytest.fixture(scope="module")
def cost_repo() -> _InMemoryCostRepo:
    return _InMemoryCostRepo()


@pytest.fixture(scope="module")
def gateway(
    ollama: OllamaManager, cost_repo: _InMemoryCostRepo, settings: Settings
) -> LiteLLMGateway:
    # Ensure Gemini key is set for litellm (it reads GEMINI_API_KEY)
    if settings.has_gemini and not os.environ.get("GEMINI_API_KEY"):
        os.environ["GEMINI_API_KEY"] = settings.google_gemini_api_key
    cost_tracker = CostTracker(cost_repo)
    return LiteLLMGateway(ollama=ollama, cost_tracker=cost_tracker, settings=settings)


SIMPLE_MESSAGES = [
    {"role": "user", "content": "What is 2+2? Answer with just the number."}
]


# ══════════════════════════════════════════════════════════
# Anthropic (Claude) Tests
# ══════════════════════════════════════════════════════════


class TestAnthropicLive:
    async def test_claude_haiku_completion(
        self, gateway: LiteLLMGateway, settings: Settings
    ) -> None:
        """LOW tier: Claude Haiku — cheapest Anthropic model."""
        if not settings.has_anthropic:
            pytest.skip("ANTHROPIC_API_KEY not set")
        result = await _try_complete(gateway, "claude-haiku-4-5-20251001", SIMPLE_MESSAGES)
        assert result.content, "Response content should not be empty"
        assert "4" in result.content
        assert result.model == "claude-haiku-4-5-20251001"
        assert result.prompt_tokens > 0
        assert result.completion_tokens > 0
        print(f"\n  Haiku: {result.content[:80]}")
        print(
            f"  Tokens: {result.prompt_tokens}+{result.completion_tokens},"
            f" Cost: ${result.cost_usd:.6f}"
        )

    async def test_claude_sonnet_completion(
        self, gateway: LiteLLMGateway, settings: Settings
    ) -> None:
        """MEDIUM tier: Claude Sonnet — primary API model."""
        if not settings.has_anthropic:
            pytest.skip("ANTHROPIC_API_KEY not set")
        result = await _try_complete(gateway, "claude-sonnet-4-6", SIMPLE_MESSAGES)
        assert result.content, "Response content should not be empty"
        assert "4" in result.content
        assert result.model == "claude-sonnet-4-6"
        print(f"\n  Sonnet: {result.content[:80]}")
        print(
            f"  Tokens: {result.prompt_tokens}+{result.completion_tokens},"
            f" Cost: ${result.cost_usd:.6f}"
        )

    async def test_claude_route_complex_reasoning(
        self, gateway: LiteLLMGateway, settings: Settings
    ) -> None:
        """COMPLEX_REASONING should route to Claude Sonnet when key is available."""
        if not settings.has_anthropic:
            pytest.skip("ANTHROPIC_API_KEY not set")
        model = await gateway.route(TaskType.COMPLEX_REASONING, budget_remaining=50.0)
        assert model == "claude-sonnet-4-6"
        print(f"\n  COMPLEX_REASONING routed to: {model}")


# ══════════════════════════════════════════════════════════
# OpenAI (GPT) Tests
# ══════════════════════════════════════════════════════════


class TestOpenAILive:
    async def test_o4_mini_completion(
        self, gateway: LiteLLMGateway, settings: Settings
    ) -> None:
        """MEDIUM tier: o4-mini (reasoning)."""
        if not settings.has_openai:
            pytest.skip("OPENAI_API_KEY not set")
        result = await _try_complete(gateway, "o4-mini", SIMPLE_MESSAGES)
        assert result.content, "Response content should not be empty"
        assert "4" in result.content
        assert result.model == "o4-mini"
        print(f"\n  o4-mini: {result.content[:80]}")
        print(
            f"  Tokens: {result.prompt_tokens}+{result.completion_tokens},"
            f" Cost: ${result.cost_usd:.6f}"
        )

    async def test_o3_completion(
        self, gateway: LiteLLMGateway, settings: Settings
    ) -> None:
        """HIGH tier: o3 (reasoning)."""
        if not settings.has_openai:
            pytest.skip("OPENAI_API_KEY not set")
        result = await _try_complete(gateway, "o3", SIMPLE_MESSAGES)
        assert result.content, "Response content should not be empty"
        assert "4" in result.content
        assert result.model == "o3"
        print(f"\n  o3: {result.content[:80]}")
        print(
            f"  Tokens: {result.prompt_tokens}+{result.completion_tokens},"
            f" Cost: ${result.cost_usd:.6f}"
        )


# ══════════════════════════════════════════════════════════
# Google Gemini Tests
# ══════════════════════════════════════════════════════════


class TestGeminiLive:
    async def test_gemini_3_flash_completion(
        self, gateway: LiteLLMGateway, settings: Settings
    ) -> None:
        """LOW tier: Gemini 3 Flash."""
        if not settings.has_gemini:
            pytest.skip("GOOGLE_GEMINI_API_KEY not set")
        result = await _try_complete(gateway, "gemini/gemini-3-flash-preview", SIMPLE_MESSAGES)
        assert result.content, "Response content should not be empty"
        assert "4" in result.content
        assert result.model == "gemini/gemini-3-flash-preview"
        print(f"\n  Gemini 3 Flash: {result.content[:80]}")
        print(
            f"  Tokens: {result.prompt_tokens}+{result.completion_tokens},"
            f" Cost: ${result.cost_usd:.6f}"
        )

    async def test_gemini_3_pro_completion(
        self, gateway: LiteLLMGateway, settings: Settings
    ) -> None:
        """MEDIUM tier: Gemini 3 Pro."""
        if not settings.has_gemini:
            pytest.skip("GOOGLE_GEMINI_API_KEY not set")
        result = await _try_complete(gateway, "gemini/gemini-3-pro-preview", SIMPLE_MESSAGES)
        assert result.content, "Response content should not be empty"
        assert "4" in result.content
        assert result.model == "gemini/gemini-3-pro-preview"
        print(f"\n  Gemini 3 Pro: {result.content[:80]}")
        print(
            f"  Tokens: {result.prompt_tokens}+{result.completion_tokens},"
            f" Cost: ${result.cost_usd:.6f}"
        )


# ══════════════════════════════════════════════════════════
# Cost Tracking Tests
# ══════════════════════════════════════════════════════════


class TestCostTracking:
    async def test_api_call_records_nonzero_cost(
        self, gateway: LiteLLMGateway, settings: Settings
    ) -> None:
        """API calls should record cost_usd > 0."""
        if not settings.has_anthropic:
            pytest.skip("ANTHROPIC_API_KEY not set")
        repo = _InMemoryCostRepo()
        tracker = CostTracker(repo)
        gw = LiteLLMGateway(
            ollama=OllamaManager(), cost_tracker=tracker, settings=settings
        )

        result = await _try_complete(gw, "claude-haiku-4-5-20251001", SIMPLE_MESSAGES)
        assert result.cost_usd > 0, f"API cost should be > 0, got {result.cost_usd}"
        assert len(repo._records) == 1
        assert repo._records[0].cost_usd > 0
        print(f"\n  API cost recorded: ${result.cost_usd:.6f}")

    async def test_local_call_records_zero_cost(
        self, gateway: LiteLLMGateway, ollama: OllamaManager
    ) -> None:
        """Ollama calls should record cost_usd == 0."""
        if not await ollama.is_running():
            pytest.skip("Ollama not running")
        repo = _InMemoryCostRepo()
        tracker = CostTracker(repo)
        settings = Settings()
        gw = LiteLLMGateway(ollama=ollama, cost_tracker=tracker, settings=settings)

        result = await gw.complete(messages=SIMPLE_MESSAGES)  # defaults to Ollama
        assert result.cost_usd == 0.0, f"Ollama cost should be 0, got {result.cost_usd}"
        assert result.model.startswith("ollama/")
        print(f"\n  Local cost: ${result.cost_usd:.6f} (model: {result.model})")


# ══════════════════════════════════════════════════════════
# Routing & Availability Tests
# ══════════════════════════════════════════════════════════


class TestRoutingLive:
    async def test_route_with_all_providers(
        self, gateway: LiteLLMGateway, settings: Settings
    ) -> None:
        """When API keys are set, routing should select appropriate models per task type."""
        if not settings.has_anthropic:
            pytest.skip("ANTHROPIC_API_KEY not set")

        routes = {}
        for task_type in TaskType:
            model = await gateway.route(task_type, budget_remaining=50.0)
            routes[task_type.value] = model

        print("\n  Routing results:")
        for task, model in routes.items():
            print(f"    {task:25s} -> {model}")

        # COMPLEX_REASONING should use MEDIUM+ tier (not free)
        assert not routes[TaskType.COMPLEX_REASONING.value].startswith("ollama/")
        # SIMPLE_QA with local_first should prefer Ollama
        if settings.local_first:
            assert routes[TaskType.SIMPLE_QA.value].startswith("ollama/")

    async def test_list_models_all_available(
        self, gateway: LiteLLMGateway, settings: Settings, ollama: OllamaManager
    ) -> None:
        """With keys + Ollama, list_models should return models from multiple providers."""
        if not settings.has_anthropic:
            pytest.skip("ANTHROPIC_API_KEY not set")
        if not await ollama.is_running():
            pytest.skip("Ollama not running")

        models = await gateway.list_models()
        print(f"\n  Available models ({len(models)}):")
        for m in models:
            print(f"    - {m}")

        # Should have models from at least Ollama + Anthropic
        assert any(m.startswith("ollama/") for m in models), "Should have Ollama models"
        assert any("claude" in m for m in models), "Should have Claude models"

        # With Ollama + Anthropic: at least 2 Ollama + 3 Claude = 5
        # With all providers: up to 2 Ollama + 3 Claude + 2 GPT + 2 Gemini = 9+
        assert len(models) >= 5, f"Expected 5+ models, got {len(models)}"
