"""Cost tracking endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from interface.api.schemas import CostLogEntry, CostLogResponse, CostSummaryResponse

router = APIRouter(prefix="/api/cost", tags=["cost"])


def _container(request: Request):  # noqa: ANN202
    return request.app.state.container


@router.get("", response_model=CostSummaryResponse)
async def cost_summary(request: Request) -> CostSummaryResponse:
    c = _container(request)
    daily = await c.cost_repo.get_daily_total()
    monthly = await c.cost_repo.get_monthly_total()
    local_rate = await c.cost_repo.get_local_usage_rate()
    budget = c.settings.default_monthly_budget_usd
    return CostSummaryResponse(
        daily_total_usd=daily,
        monthly_total_usd=monthly,
        local_usage_rate=local_rate,
        monthly_budget_usd=budget,
        budget_remaining_usd=max(budget - monthly, 0.0),
    )


@router.get("/logs", response_model=CostLogResponse)
async def cost_logs(request: Request, limit: int = 50) -> CostLogResponse:
    c = _container(request)
    records = await c.cost_repo.list_recent(limit=limit)
    entries = [CostLogEntry.from_record(r) for r in records]
    return CostLogResponse(logs=entries, count=len(entries))
