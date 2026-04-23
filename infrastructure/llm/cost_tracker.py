"""Cost tracker — records and queries LLM + engine usage costs."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from domain.entities.cost import CostRecord
from domain.ports.agent_engine import AgentEngineResult
from domain.ports.cost_repository import CostRepository
from domain.ports.engine_cost_recorder import EngineCostRecorderPort
from domain.ports.llm_gateway import LLMResponse

logger = logging.getLogger(__name__)


class CostTracker(EngineCostRecorderPort):
    """Track LLM and engine call costs via CostRepository port.

    Converts LLMResponse/AgentEngineResult → CostRecord, delegates persistence.
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
            timestamp=datetime.now(UTC),
        )
        await self._repo.save(record)

    async def record_engine_result(self, result: AgentEngineResult) -> None:
        """Convert AgentEngineResult to CostRecord and persist.

        Records engine execution costs that were previously invisible to
        daily/monthly aggregation and budget checks (BUG-002 fix).
        """
        is_local = result.engine.value == "ollama"
        record = CostRecord.from_engine_result(
            engine_type=result.engine.value,
            model_used=result.model_used,
            cost_usd=result.cost_usd,
            is_local=is_local,
        )
        try:
            await self._repo.save(record)
        except Exception:
            logger.warning(
                "Failed to record engine cost for %s — continuing",
                result.engine.value,
                exc_info=True,
            )

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
