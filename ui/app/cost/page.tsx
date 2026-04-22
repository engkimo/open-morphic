"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  getCostSummary,
  getCostLogs,
  listTasks,
  type CostSummary,
  type CostLogEntry,
} from "@/lib/api";
import { useAutoRefresh } from "@/lib/useAutoRefresh";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";

function BudgetBar({ cost }: { cost: CostSummary }) {
  const pct =
    cost.monthly_budget_usd > 0
      ? (cost.monthly_total_usd / cost.monthly_budget_usd) * 100
      : 0;
  const indicatorColor =
    pct > 90
      ? "bg-danger"
      : pct > 70
        ? "bg-warning"
        : "bg-accent";

  return (
    <Card>
      <CardHeader className="p-3">
        <CardTitle className="text-sm font-semibold uppercase tracking-wide text-text-muted">
          Monthly Budget
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-end justify-between mb-2">
          <div>
            <span className="text-lg font-bold font-mono">
              ${cost.monthly_total_usd.toFixed(4)}
            </span>
            <span className="text-text-muted text-sm ml-2">
              / ${cost.monthly_budget_usd.toFixed(2)}
            </span>
          </div>
          <span className="text-sm text-text-muted">
            {Math.round(pct)}% used
          </span>
        </div>
        <Progress value={pct} indicatorClassName={indicatorColor} />
        <div className="mt-2 text-xs text-text-muted">
          Remaining: ${cost.budget_remaining_usd.toFixed(4)}
        </div>
      </CardContent>
    </Card>
  );
}

function SummaryCards({ cost }: { cost: CostSummary }) {
  const localPct = Math.round(cost.local_usage_rate * 100);

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardContent className="p-3 text-center">
          <div className="text-lg font-bold font-mono">
            ${cost.daily_total_usd.toFixed(4)}
          </div>
          <div className="text-xs text-text-muted mt-1">Today</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-3 text-center">
          <div className="text-lg font-bold font-mono">
            ${cost.monthly_total_usd.toFixed(4)}
          </div>
          <div className="text-xs text-text-muted mt-1">This Month</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-3 text-center">
          <div className="text-lg font-bold font-mono text-local-free">
            {localPct}%
          </div>
          <div className="text-xs text-text-muted mt-1">Local Usage</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-3 text-center">
          <div className="text-lg font-bold font-mono text-success">
            ${cost.budget_remaining_usd.toFixed(2)}
          </div>
          <div className="text-xs text-text-muted mt-1">Remaining</div>
        </CardContent>
      </Card>
    </div>
  );
}

function ModelDistribution({ logs }: { logs: CostLogEntry[] }) {
  const distribution = new Map<string, { count: number; cost: number }>();
  for (const log of logs) {
    const entry = distribution.get(log.model) || { count: 0, cost: 0 };
    entry.count++;
    entry.cost += log.cost_usd;
    distribution.set(log.model, entry);
  }

  const sorted = Array.from(distribution.entries()).sort(
    ([, a], [, b]) => b.count - a.count,
  );

  if (sorted.length === 0) return null;

  const maxCount = Math.max(...sorted.map(([, v]) => v.count));

  return (
    <Card>
      <CardHeader className="p-3">
        <CardTitle className="text-sm font-semibold uppercase tracking-wide text-text-muted">
          Model Distribution
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {sorted.map(([model, data]) => {
            const pct = maxCount > 0 ? (data.count / maxCount) * 100 : 0;
            const isLocal = model.startsWith("ollama/") || model.startsWith("ollama_");

            return (
              <div key={model}>
                <div className="flex items-center justify-between text-xs mb-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono">{model}</span>
                    {isLocal && (
                      <Badge variant="free" className="text-[9px] px-1.5 py-0">FREE</Badge>
                    )}
                  </div>
                  <span className="text-text-muted">
                    {data.count}x / ${data.cost.toFixed(4)}
                  </span>
                </div>
                <Progress
                  value={pct}
                  indicatorClassName={isLocal ? "bg-local-free" : "bg-accent"}
                />
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

export default function CostPage() {
  const [cost, setCost] = useState<CostSummary | null>(null);
  const [logs, setLogs] = useState<CostLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [hasActive, setHasActive] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [costData, logData, taskData] = await Promise.all([
        getCostSummary(),
        getCostLogs(100),
        listTasks(),
      ]);
      setCost(costData);
      setLogs(logData.logs);
      setHasActive(
        taskData.tasks.some(
          (t) => t.status === "running" || t.status === "pending",
        ),
      );
    } catch {
      /* backend may be down */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // TD-170: Auto-refresh when tasks are running/pending
  useAutoRefresh(refresh, hasActive);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/" className="text-sm text-text-muted hover:text-accent">
            &larr; Dashboard
          </Link>
          <h1 className="font-mono text-lg font-semibold tracking-tight">
            Cost Dashboard
          </h1>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={refresh}
          disabled={loading}
        >
          {loading ? "Loading..." : "Refresh"}
        </Button>
      </div>

      {loading && (
        <p className="py-8 text-center text-sm text-text-muted">Loading...</p>
      )}

      {!loading && cost && (
        <>
          <SummaryCards cost={cost} />
          <BudgetBar cost={cost} />
          <ModelDistribution logs={logs} />

          {/* Cost Log Table */}
          <Card>
            <CardHeader className="p-3">
              <CardTitle className="text-sm font-semibold uppercase tracking-wide text-text-muted">
                Recent Cost Logs ({logs.length})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {logs.length === 0 ? (
                <p className="py-4 text-center text-sm text-text-muted">
                  No cost records yet.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Model</TableHead>
                      <TableHead className="text-right">Prompt</TableHead>
                      <TableHead className="text-right">Completion</TableHead>
                      <TableHead className="text-right">Cost</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Time</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {logs.map((log, i) => (
                      <TableRow key={`${log.timestamp}-${i}`}>
                        <TableCell className="font-mono text-xs">
                          {log.model}
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs">
                          {log.prompt_tokens.toLocaleString()}
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs">
                          {log.completion_tokens.toLocaleString()}
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs">
                          {log.cost_usd === 0 ? (
                            <span className="text-local-free">$0.00</span>
                          ) : (
                            <span>${log.cost_usd.toFixed(6)}</span>
                          )}
                        </TableCell>
                        <TableCell>
                          {log.is_local ? (
                            <Badge variant="free" className="text-[10px]">LOCAL</Badge>
                          ) : (
                            <Badge variant="info" className="text-[10px]">API</Badge>
                          )}
                        </TableCell>
                        <TableCell className="text-xs text-text-muted">
                          {new Date(log.timestamp).toLocaleTimeString()}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {!loading && !cost && (
        <p className="py-8 text-center text-sm text-text-muted">
          Could not load cost data. Is the backend running?
        </p>
      )}
    </div>
  );
}
