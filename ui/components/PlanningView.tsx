"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { approvePlan, rejectPlan, type ExecutionPlanResponse } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

interface PlanningViewProps {
  plan: ExecutionPlanResponse;
}

const STATUS_VARIANT: Record<string, "info" | "success" | "destructive"> = {
  proposed: "info",
  approved: "success",
  rejected: "destructive",
};

export default function PlanningView({ plan: initialPlan }: PlanningViewProps) {
  const router = useRouter();
  const [plan, setPlan] = useState(initialPlan);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isDecided = plan.status !== "proposed";

  async function handleApprove() {
    setLoading(true);
    setError(null);
    try {
      const task = await approvePlan(plan.id);
      router.push(`/tasks/${task.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to approve");
    } finally {
      setLoading(false);
    }
  }

  async function handleReject() {
    setLoading(true);
    setError(null);
    try {
      const updated = await rejectPlan(plan.id);
      setPlan(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reject");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">{plan.goal}</CardTitle>
          <Badge variant={STATUS_VARIANT[plan.status] || "secondary"}>
            {plan.status}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Steps table */}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>#</TableHead>
              <TableHead>Description</TableHead>
              <TableHead>Model</TableHead>
              <TableHead className="text-right">Est. Cost</TableHead>
              <TableHead className="text-right">Tokens</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {plan.steps.map((step, i) => (
              <TableRow key={i}>
                <TableCell className="text-text-muted">{i + 1}</TableCell>
                <TableCell>{step.subtask_description}</TableCell>
                <TableCell>
                  <span className="text-text-muted">{step.proposed_model}</span>
                  {step.proposed_model.startsWith("ollama/") && (
                    <Badge variant="free" className="ml-1 text-[10px] px-1 py-0">
                      FREE
                    </Badge>
                  )}
                </TableCell>
                <TableCell
                  className={cn(
                    "text-right font-mono",
                    step.estimated_cost_usd === 0
                      ? "text-success"
                      : "text-warning",
                  )}
                >
                  ${step.estimated_cost_usd.toFixed(4)}
                </TableCell>
                <TableCell className="text-right text-text-muted">
                  {step.estimated_tokens.toLocaleString()}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>

        {/* Total cost */}
        <div className="flex items-center justify-between border-t border-border pt-3">
          <span className="font-semibold text-text">Total Estimated Cost</span>
          <span
            className={cn(
              "text-lg font-bold",
              plan.total_estimated_cost_usd === 0
                ? "text-success"
                : "text-warning",
            )}
          >
            ${plan.total_estimated_cost_usd.toFixed(4)}
          </span>
        </div>

        {/* Action buttons */}
        {error && <p className="text-sm text-destructive">{error}</p>}

        {!isDecided && (
          <div className="flex gap-3">
            <Button onClick={handleApprove} disabled={loading}>
              {loading ? "..." : "Approve"}
            </Button>
            <Button
              variant="outline"
              onClick={handleReject}
              disabled={loading}
            >
              Reject
            </Button>
          </div>
        )}

        {plan.task_id && (
          <p className="text-sm text-text-muted">
            Task ID:{" "}
            <a
              href={`/tasks/${plan.task_id}`}
              className="text-accent hover:underline"
            >
              {plan.task_id.slice(0, 8)}
            </a>
          </p>
        )}
      </CardContent>
    </Card>
  );
}
