"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { listPlans, type ExecutionPlanResponse } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

const STATUS_VARIANT: Record<string, "info" | "success" | "destructive" | "default" | "secondary"> = {
  proposed: "info",
  approved: "success",
  rejected: "destructive",
  executed: "default",
};

function PlanCard({ plan }: { plan: ExecutionPlanResponse }) {
  const isFree = plan.total_estimated_cost_usd === 0;

  return (
    <Link href={`/plans/${plan.id}`} className="block">
      <Card className="transition-colors hover:border-accent">
        <CardContent className="p-3">
          <div className="flex items-center justify-between mb-2">
            <Badge variant={STATUS_VARIANT[plan.status] || "secondary"}>
              {plan.status}
            </Badge>
            <span className="text-[10px] text-text-muted">
              {new Date(plan.created_at).toLocaleString()}
            </span>
          </div>
          <h3 className="font-mono text-sm font-semibold mb-2 line-clamp-2">
            {plan.goal}
          </h3>
          <div className="flex items-center gap-4 text-xs text-text-muted">
            <span>{plan.steps.length} step{plan.steps.length !== 1 ? "s" : ""}</span>
            {isFree ? (
              <Badge variant="free" className="text-[10px]">$0.00 FREE</Badge>
            ) : (
              <span className="font-mono">${plan.total_estimated_cost_usd.toFixed(4)}</span>
            )}
            {plan.task_id && (
              <span className="text-accent">
                Task: {plan.task_id.slice(0, 8)}...
              </span>
            )}
          </div>
          {plan.steps.length > 0 && (
            <div className="mt-2 space-y-1">
              {plan.steps.slice(0, 3).map((step, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 text-[10px] text-text-muted"
                >
                  <span className="text-accent font-mono">{i + 1}.</span>
                  <span className="truncate">{step.subtask_description}</span>
                  <span className="flex-shrink-0 font-mono">
                    {step.proposed_model.startsWith("ollama/") ? (
                      <Badge variant="free" className="text-[9px] px-1 py-0">FREE</Badge>
                    ) : (
                      `$${step.estimated_cost_usd.toFixed(4)}`
                    )}
                  </span>
                </div>
              ))}
              {plan.steps.length > 3 && (
                <div className="text-[10px] text-text-muted">
                  +{plan.steps.length - 3} more steps
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </Link>
  );
}

export default function PlansPage() {
  const [plans, setPlans] = useState<ExecutionPlanResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("all");

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listPlans();
      setPlans(data.plans);
    } catch {
      /* backend may be down */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const filtered =
    filter === "all" ? plans : plans.filter((p) => p.status === filter);

  const counts = {
    all: plans.length,
    proposed: plans.filter((p) => p.status === "proposed").length,
    approved: plans.filter((p) => p.status === "approved").length,
    rejected: plans.filter((p) => p.status === "rejected").length,
    executed: plans.filter((p) => p.status === "executed").length,
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="link" size="sm" asChild>
            <Link href="/">&larr; Dashboard</Link>
          </Button>
          <h1 className="font-mono text-lg font-semibold tracking-tight">
            Execution Plans
          </h1>
        </div>
        <Button onClick={refresh} disabled={loading}>
          {loading ? "Loading..." : "Refresh"}
        </Button>
      </div>

      {/* Filter tabs */}
      <Tabs value={filter} onValueChange={setFilter}>
        <TabsList>
          {(["all", "proposed", "approved", "executed", "rejected"] as const).map(
            (status) => (
              <TabsTrigger key={status} value={status}>
                {status.charAt(0).toUpperCase() + status.slice(1)} ({counts[status]})
              </TabsTrigger>
            ),
          )}
        </TabsList>
      </Tabs>

      {/* Plans grid */}
      {loading ? (
        <p className="py-8 text-center text-sm text-text-muted">Loading...</p>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center">
            <p className="text-sm text-text-muted">
              {plans.length === 0
                ? 'No plans yet. Use "Plan First" mode on the dashboard to create one.'
                : "No plans match this filter."}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((plan) => (
            <PlanCard key={plan.id} plan={plan} />
          ))}
        </div>
      )}
    </div>
  );
}
