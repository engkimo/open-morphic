"""Tests for LiteLLMGateway — multi-model routing and LLM completion."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domain.value_objects.model_tier import TaskType
from infrastructure.llm.cost_tracker import CostTracker
from infrastructure.llm.litellm_gateway import LiteLLMGateway
from infrastructure.llm.ollama_manager import OllamaManager
from shared.config import Settings

# Default model returned when Ollama is running and has qwen3-coder:30b
DEFAULT_OLLAMA = "ollama/qwen3-coder:30b"
ALL_OLLAMA_MODELS = ["qwen3-coder:30b", "qwen3:8b", "deepseek-r1:8b", "llama3.2:3b"]


@pytest.fixture
def ollama() -> AsyncMock:
    mock = AsyncMock(spec=OllamaManager)
    mock.list_models.return_value = ALL_OLLAMA_MODELS
    return mock


@pytest.fixture
def cost_tracker() -> AsyncMock:
    return AsyncMock(spec=CostTracker)


@pytest.fixture
def settings() -> Settings:
    """Settings with no API keys, local_first=True."""
    return Settings(
        local_first=True,
        anthropic_api_key="",
        openai_api_key="",
        google_gemini_api_key="",
    )


@pytest.fixture
def gateway(
    ollama: AsyncMock, cost_tracker: AsyncMock, settings: Settings
) -> LiteLLMGateway:
    return LiteLLMGateway(ollama, cost_tracker, settings)


def _mock_litellm_response(
    content: str = "Hello!", prompt_tokens: int = 10, completion_tokens: int = 5, cost: float = 0.0
) -> MagicMock:
    """Create a mock LiteLLM ModelResponse."""
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=content))]
    resp.usage = MagicMock(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    resp._hidden_params = {"response_cost": cost}
    return resp


class TestRoute:
    async def test_returns_ollama_when_local_first(
        self, gateway: LiteLLMGateway, ollama: AsyncMock
    ) -> None:
        ollama.is_running.return_value = True
        model = await gateway.route(TaskType.SIMPLE_QA, budget_remaining=50.0)
        assert model == DEFAULT_OLLAMA

    async def test_forces_free_when_budget_exhausted(
        self, gateway: LiteLLMGateway
    ) -> None:
        model = await gateway.route(TaskType.COMPLEX_REASONING, budget_remaining=0.0)
        assert model == DEFAULT_OLLAMA

    async def test_forces_free_when_negative_budget(
        self, gateway: LiteLLMGateway
    ) -> None:
        model = await gateway.route(TaskType.COMPLEX_REASONING, budget_remaining=-5.0)
        assert model == DEFAULT_OLLAMA

    async def test_falls_back_to_free_when_no_api_keys(
        self, gateway: LiteLLMGateway, ollama: AsyncMock
    ) -> None:
        ollama.is_running.return_value = False
        model = await gateway.route(TaskType.COMPLEX_REASONING, budget_remaining=50.0)
        assert model == DEFAULT_OLLAMA

    async def test_routes_to_api_when_available(
        self, ollama: AsyncMock, cost_tracker: AsyncMock
    ) -> None:
        s = Settings(
            local_first=False,
            anthropic_api_key="sk-test",
            openai_api_key="",
            google_gemini_api_key="",
        )
        gw = LiteLLMGateway(ollama, cost_tracker, s)
        ollama.is_running.return_value = False
        model = await gw.route(TaskType.COMPLEX_REASONING, budget_remaining=50.0)
        assert model == "claude-sonnet-4-6"

    async def test_complex_reasoning_skips_free_even_with_local_first(
        self, ollama: AsyncMock, cost_tracker: AsyncMock
    ) -> None:
        """COMPLEX_REASONING = (MEDIUM, HIGH). FREE not in tiers → skip Ollama shortcut."""
        s = Settings(
            local_first=True,
            anthropic_api_key="sk-test",
            openai_api_key="",
            google_gemini_api_key="",
        )
        gw = LiteLLMGateway(ollama, cost_tracker, s)
        ollama.is_running.return_value = True
        model = await gw.route(TaskType.COMPLEX_REASONING, budget_remaining=50.0)
        assert model == "claude-sonnet-4-6"

    async def test_code_generation_prefers_ollama(
        self, gateway: LiteLLMGateway, ollama: AsyncMock
    ) -> None:
        """CODE_GENERATION = (FREE, MEDIUM). With local_first, routes to Ollama."""
        ollama.is_running.return_value = True
        model = await gateway.route(TaskType.CODE_GENERATION, budget_remaining=50.0)
        assert model == DEFAULT_OLLAMA


class TestComplete:
    async def test_returns_llm_response(
        self, gateway: LiteLLMGateway, cost_tracker: AsyncMock
    ) -> None:
        with patch("infrastructure.llm.litellm_gateway.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                return_value=_mock_litellm_response()
            )
            result = await gateway.complete(
                messages=[{"role": "user", "content": "Hi"}],
                model="ollama/qwen3:8b",
            )

        assert result.content == "Hello!"
        assert result.model == "ollama/qwen3:8b"
        assert result.prompt_tokens == 10
        assert result.completion_tokens == 5
        cost_tracker.record.assert_awaited_once()

    async def test_sets_api_base_for_ollama(self, gateway: LiteLLMGateway) -> None:
        with patch("infrastructure.llm.litellm_gateway.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                return_value=_mock_litellm_response()
            )
            await gateway.complete(
                messages=[{"role": "user", "content": "test"}],
                model="ollama/qwen3:8b",
            )

            call_kwargs = mock_litellm.acompletion.call_args[1]
            assert "api_base" in call_kwargs

    async def test_strips_temperature_for_o_series(self, gateway: LiteLLMGateway) -> None:
        with patch("infrastructure.llm.litellm_gateway.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                return_value=_mock_litellm_response(cost=0.01)
            )
            await gateway.complete(
                messages=[{"role": "user", "content": "test"}],
                model="o4-mini",
                temperature=0.7,
            )

            call_kwargs = mock_litellm.acompletion.call_args[1]
            assert "temperature" not in call_kwargs

    async def test_keeps_temperature_for_non_o_series(self, gateway: LiteLLMGateway) -> None:
        with patch("infrastructure.llm.litellm_gateway.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                return_value=_mock_litellm_response(cost=0.003)
            )
            await gateway.complete(
                messages=[{"role": "user", "content": "test"}],
                model="claude-sonnet-4-6",
                temperature=0.5,
            )

            call_kwargs = mock_litellm.acompletion.call_args[1]
            assert call_kwargs["temperature"] == 0.5

    async def test_no_api_base_for_cloud_models(self, gateway: LiteLLMGateway) -> None:
        with patch("infrastructure.llm.litellm_gateway.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                return_value=_mock_litellm_response(cost=0.003)
            )
            await gateway.complete(
                messages=[{"role": "user", "content": "test"}],
                model="claude-sonnet-4-6",
            )

            call_kwargs = mock_litellm.acompletion.call_args[1]
            assert "api_base" not in call_kwargs

    async def test_defaults_to_ollama_model(self, gateway: LiteLLMGateway) -> None:
        with patch("infrastructure.llm.litellm_gateway.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                return_value=_mock_litellm_response()
            )
            result = await gateway.complete(
                messages=[{"role": "user", "content": "test"}],
            )
            assert result.model == DEFAULT_OLLAMA

    async def test_extracts_cost_from_response(
        self, gateway: LiteLLMGateway, cost_tracker: AsyncMock
    ) -> None:
        with patch("infrastructure.llm.litellm_gateway.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                return_value=_mock_litellm_response(cost=0.005)
            )
            result = await gateway.complete(
                messages=[{"role": "user", "content": "test"}],
                model="claude-sonnet-4-6",
            )
            assert result.cost_usd == pytest.approx(0.005)


class TestIsAvailable:
    async def test_ollama_available_when_running_and_installed(
        self, gateway: LiteLLMGateway, ollama: AsyncMock
    ) -> None:
        ollama.is_running.return_value = True
        assert await gateway.is_available("ollama/qwen3:8b") is True

    async def test_ollama_unavailable_when_not_installed(
        self, gateway: LiteLLMGateway, ollama: AsyncMock
    ) -> None:
        ollama.is_running.return_value = True
        ollama.list_models.return_value = ["qwen3:8b"]  # no coder model
        assert await gateway.is_available("ollama/qwen3-coder:30b") is False

    async def test_ollama_unavailable_when_down(
        self, gateway: LiteLLMGateway, ollama: AsyncMock
    ) -> None:
        ollama.is_running.return_value = False
        assert await gateway.is_available("ollama/qwen3:8b") is False

    async def test_claude_available_with_key(
        self, ollama: AsyncMock, cost_tracker: AsyncMock
    ) -> None:
        s = Settings(
            anthropic_api_key="sk-test",
            openai_api_key="",
            google_gemini_api_key="",
        )
        gw = LiteLLMGateway(ollama, cost_tracker, s)
        assert await gw.is_available("claude-sonnet-4-6") is True

    async def test_claude_unavailable_without_key(
        self, gateway: LiteLLMGateway
    ) -> None:
        assert await gateway.is_available("claude-sonnet-4-6") is False

    async def test_o4_mini_available_with_key(
        self, ollama: AsyncMock, cost_tracker: AsyncMock
    ) -> None:
        s = Settings(
            anthropic_api_key="",
            openai_api_key="sk-test",
            google_gemini_api_key="",
        )
        gw = LiteLLMGateway(ollama, cost_tracker, s)
        assert await gw.is_available("o4-mini") is True

    async def test_o3_available_with_key(
        self, ollama: AsyncMock, cost_tracker: AsyncMock
    ) -> None:
        s = Settings(
            anthropic_api_key="",
            openai_api_key="sk-test",
            google_gemini_api_key="",
        )
        gw = LiteLLMGateway(ollama, cost_tracker, s)
        assert await gw.is_available("o3") is True

    async def test_gemini_available_with_key(
        self, ollama: AsyncMock, cost_tracker: AsyncMock
    ) -> None:
        s = Settings(
            anthropic_api_key="",
            openai_api_key="",
            google_gemini_api_key="key-test",
        )
        gw = LiteLLMGateway(ollama, cost_tracker, s)
        assert await gw.is_available("gemini/gemini-3-flash-preview") is True

    async def test_unknown_model_unavailable(self, gateway: LiteLLMGateway) -> None:
        assert await gateway.is_available("some-unknown-model") is False


class TestListModels:
    async def test_returns_only_available(
        self, ollama: AsyncMock, cost_tracker: AsyncMock
    ) -> None:
        s = Settings(
            anthropic_api_key="sk-test",
            openai_api_key="",
            google_gemini_api_key="",
        )
        gw = LiteLLMGateway(ollama, cost_tracker, s)
        ollama.is_running.return_value = True

        models = await gw.list_models()
        # Available: 4 Ollama + 3 Claude (haiku, sonnet, opus) = 7
        assert DEFAULT_OLLAMA in models
        assert "ollama/qwen3:8b" in models
        assert "claude-sonnet-4-6" in models
        assert "o3" not in models  # no OpenAI key
        assert len(models) == 7

    async def test_returns_all_providers(
        self, ollama: AsyncMock, cost_tracker: AsyncMock
    ) -> None:
        s = Settings(
            anthropic_api_key="sk-test",
            openai_api_key="sk-test",
            google_gemini_api_key="key-test",
        )
        gw = LiteLLMGateway(ollama, cost_tracker, s)
        ollama.is_running.return_value = True

        models = await gw.list_models()
        # 4 Ollama + 3 Claude + 2 OpenAI (o4-mini, o3) + 2 Gemini = 11
        assert "o4-mini" in models
        assert "o3" in models
        assert "gemini/gemini-3-flash-preview" in models
        assert "gemini/gemini-3-pro-preview" in models
        assert len(models) == 11

    async def test_empty_when_nothing_available(
        self, gateway: LiteLLMGateway, ollama: AsyncMock
    ) -> None:
        ollama.is_running.return_value = False
        models = await gateway.list_models()
        assert models == []
