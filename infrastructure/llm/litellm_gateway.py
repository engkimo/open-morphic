"""LiteLLM gateway — implements LLMGateway port with LOCAL_FIRST routing."""

from __future__ import annotations

import litellm

from domain.ports.llm_gateway import LLMGateway, LLMResponse
from domain.value_objects.model_tier import ModelTier, TaskType
from infrastructure.llm.cost_tracker import CostTracker
from infrastructure.llm.ollama_manager import OllamaManager
from shared.config import Settings


class LiteLLMGateway(LLMGateway):
    """LiteLLM-based multi-model gateway with LOCAL_FIRST routing.

    Routing priority:
    1. Budget exhausted → force free (Ollama)
    2. LOCAL_FIRST + Ollama running + FREE in tier → Ollama
    3. Task type → tier cascade → first available model
    4. Ultimate fallback → Ollama
    """

    MODEL_TIERS: dict[ModelTier, list[str]] = {
        ModelTier.FREE: [
            "ollama/qwen3:8b",
            "ollama/deepseek-r1:8b",
            "ollama/llama3.2:3b",
        ],
        ModelTier.LOW: [
            "claude-haiku-4-5-20251001",
            "gemini/gemini-2.0-flash",
        ],
        ModelTier.MEDIUM: [
            "claude-sonnet-4-6",
            "gpt-4o-mini",
            "gemini/gemini-2.5-pro",
        ],
        ModelTier.HIGH: [
            "claude-opus-4-6",
            "gpt-4o",
        ],
    }

    TASK_MODEL_MAP: dict[TaskType, tuple[ModelTier, ...]] = {
        TaskType.SIMPLE_QA: (ModelTier.FREE, ModelTier.LOW),
        TaskType.CODE_GENERATION: (ModelTier.FREE, ModelTier.MEDIUM),
        TaskType.COMPLEX_REASONING: (ModelTier.MEDIUM, ModelTier.HIGH),
        TaskType.FILE_OPERATION: (ModelTier.FREE, ModelTier.LOW),
        TaskType.LONG_CONTEXT: (ModelTier.MEDIUM,),
        TaskType.MULTIMODAL: (ModelTier.MEDIUM, ModelTier.HIGH),
    }

    def __init__(
        self,
        ollama: OllamaManager,
        cost_tracker: CostTracker,
        settings: Settings,
    ) -> None:
        self._ollama = ollama
        self._cost_tracker = cost_tracker
        self._settings = settings

    async def route(self, task_type: TaskType, budget_remaining: float) -> str:
        """Select optimal model: LOCAL_FIRST → task type → budget."""
        if budget_remaining <= 0:
            return self.MODEL_TIERS[ModelTier.FREE][0]

        tiers = self.TASK_MODEL_MAP.get(
            task_type, (ModelTier.FREE, ModelTier.MEDIUM)
        )

        # LOCAL_FIRST: prefer Ollama when running and FREE is in tier
        if self._settings.local_first and await self._ollama.is_running():
            if ModelTier.FREE in tiers:
                return self.MODEL_TIERS[ModelTier.FREE][0]

        # Cascade through tiers, return first available
        for tier in tiers:
            for model in self.MODEL_TIERS[tier]:
                if await self.is_available(model):
                    return model

        # Ultimate fallback
        return self.MODEL_TIERS[ModelTier.FREE][0]

    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Execute LLM completion via LiteLLM."""
        resolved = model or self.MODEL_TIERS[ModelTier.FREE][0]

        kwargs: dict = {
            "model": resolved,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if resolved.startswith("ollama/"):
            kwargs["api_base"] = self._settings.ollama_base_url

        response = await litellm.acompletion(**kwargs)

        usage = response.usage
        cost = 0.0
        if hasattr(response, "_hidden_params") and response._hidden_params:
            cost = response._hidden_params.get("response_cost", 0.0) or 0.0

        llm_resp = LLMResponse(
            content=response.choices[0].message.content or "",
            model=resolved,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            cost_usd=cost,
            cached=False,
        )

        await self._cost_tracker.record(llm_resp)
        return llm_resp

    async def is_available(self, model: str) -> bool:
        """Check if a specific model is usable."""
        if model.startswith("ollama/"):
            return await self._ollama.is_running()
        if "claude" in model:
            return self._settings.has_anthropic
        if "gpt" in model:
            return self._settings.has_openai
        if "gemini" in model:
            return self._settings.has_gemini
        return False

    async def list_models(self) -> list[str]:
        """List all currently available models."""
        available = []
        for tier_models in self.MODEL_TIERS.values():
            for model_name in tier_models:
                if await self.is_available(model_name):
                    available.append(model_name)
        return available
