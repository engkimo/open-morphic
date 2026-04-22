"use client";

import type { CostSummary } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

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

  const indicatorColor =
    budgetPct > 90
      ? "bg-danger"
      : budgetPct > 70
        ? "bg-warning"
        : "bg-accent";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-text-muted">Cost</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
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
          <Progress
            value={Math.min(budgetPct, 100)}
            indicatorClassName={indicatorColor}
          />
        </div>
      </CardContent>
    </Card>
  );
}
