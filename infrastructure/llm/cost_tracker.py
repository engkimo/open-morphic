"""Cost tracker — records and queries LLM usage costs."""

from __future__ import annotations

from datetime import datetime, timezone

from domain.entities.cost import CostRecord
from domain.ports.cost_repository import CostRepository
from domain.ports.llm_gateway import LLMResponse


class CostTracker:
    """Track LLM call costs via CostRepository port.

    Converts LLMResponse → CostRecord, delegates persistence to repository.
    Provides budget checking against monthly totals.
    """

    def __init__(self, cost_repo: CostRepository) -> None:
        self._repo = cost_repo

    async def record(self, response: LLMResponse) -> None:
        """Convert LLMResponse to CostRecord and persist."""
        record = CostRecord(
            model=response.model,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            cost_usd=response.cost_usd,
            cached_tokens=0,
            is_local=response.model.startswith("ollama/"),
            timestamp=datetime.now(timezone.utc),
        )
        await self._repo.save(record)

    async def get_daily_total(self) -> float:
        """Total cost for today."""
        return await self._repo.get_daily_total()

    async def get_monthly_total(self) -> float:
        """Total cost for current month."""
        return await self._repo.get_monthly_total()

    async def get_local_usage_rate(self) -> float:
        """Ratio of local (Ollama) calls to total calls (0.0-1.0)."""
        return await self._repo.get_local_usage_rate()

    async def check_budget(self, monthly_budget: float) -> bool:
        """Returns True if within budget, False if exceeded."""
        total = await self._repo.get_monthly_total()
        return total < monthly_budget
