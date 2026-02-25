"use client";

import type { CostSummary } from "@/lib/api";

interface CostMeterProps {
  cost: CostSummary | null;
}

export default function CostMeter({ cost }: CostMeterProps) {
  if (!cost) return null;

  const budgetPct =
    cost.monthly_budget_usd > 0
      ? (cost.monthly_total_usd / cost.monthly_budget_usd) * 100
      : 0;
  const localPct = Math.round(cost.local_usage_rate * 100);

  return (
    <div className="rounded-lg border border-border bg-surface p-4 text-sm">
      <h3 className="mb-3 font-mono font-semibold text-text-muted">Cost</h3>
      <div className="space-y-2">
        <div className="flex justify-between">
          <span className="text-text-muted">Today</span>
          <span>${cost.daily_total_usd.toFixed(4)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-text-muted">Month</span>
          <span>${cost.monthly_total_usd.toFixed(4)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-text-muted">Local</span>
          <span className="text-local-free">{localPct}%</span>
        </div>

        {/* Budget bar */}
        <div className="mt-2">
          <div className="mb-1 flex justify-between text-xs text-text-muted">
            <span>Budget</span>
            <span>
              ${cost.budget_remaining_usd.toFixed(2)} / $
              {cost.monthly_budget_usd.toFixed(2)}
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-border">
            <div
              className="h-1.5 rounded-full transition-all"
              style={{
                width: `${Math.min(budgetPct, 100)}%`,
                backgroundColor:
                  budgetPct > 90
                    ? "var(--danger)"
                    : budgetPct > 70
                      ? "var(--warning)"
                      : "var(--accent)",
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
