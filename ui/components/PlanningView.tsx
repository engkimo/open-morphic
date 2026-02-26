"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { approvePlan, rejectPlan, type ExecutionPlanResponse } from "@/lib/api";

interface PlanningViewProps {
  plan: ExecutionPlanResponse;
}

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
    <div className="space-y-4 rounded-lg border border-border bg-surface p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-text">{plan.goal}</h2>
        <span
          className={`rounded px-2 py-0.5 text-xs font-semibold ${
            plan.status === "proposed"
              ? "bg-blue-900/50 text-blue-400"
              : plan.status === "approved"
                ? "bg-emerald-900/50 text-emerald-400"
                : "bg-red-900/50 text-red-400"
          }`}
        >
          {plan.status}
        </span>
      </div>

      {/* Steps table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text-muted">
              <th className="pb-2 pr-4">#</th>
              <th className="pb-2 pr-4">Description</th>
              <th className="pb-2 pr-4">Model</th>
              <th className="pb-2 pr-4 text-right">Est. Cost</th>
              <th className="pb-2 text-right">Tokens</th>
            </tr>
          </thead>
          <tbody>
            {plan.steps.map((step, i) => (
              <tr key={i} className="border-b border-border/50">
                <td className="py-2 pr-4 text-text-muted">{i + 1}</td>
                <td className="py-2 pr-4 text-text">
                  {step.subtask_description}
                </td>
                <td className="py-2 pr-4">
                  <span className="text-text-muted">{step.proposed_model}</span>
                  {step.proposed_model.startsWith("ollama/") && (
                    <span className="ml-1 rounded bg-emerald-900/50 px-1 py-0.5 text-[10px] font-bold text-emerald-400">
                      FREE
                    </span>
                  )}
                </td>
                <td
                  className={`py-2 pr-4 text-right ${
                    step.estimated_cost_usd === 0
                      ? "text-emerald-400"
                      : "text-amber-400"
                  }`}
                >
                  ${step.estimated_cost_usd.toFixed(4)}
                </td>
                <td className="py-2 text-right text-text-muted">
                  {step.estimated_tokens.toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Total cost */}
      <div className="flex items-center justify-between border-t border-border pt-3">
        <span className="font-semibold text-text">Total Estimated Cost</span>
        <span
          className={`text-lg font-bold ${
            plan.total_estimated_cost_usd === 0
              ? "text-emerald-400"
              : "text-amber-400"
          }`}
        >
          ${plan.total_estimated_cost_usd.toFixed(4)}
        </span>
      </div>

      {/* Action buttons */}
      {error && <p className="text-sm text-red-400">{error}</p>}

      {!isDecided && (
        <div className="flex gap-3">
          <button
            onClick={handleApprove}
            disabled={loading}
            className="rounded-lg bg-accent px-4 py-2 font-semibold text-white hover:bg-accent/80 disabled:opacity-50"
          >
            {loading ? "..." : "Approve"}
          </button>
          <button
            onClick={handleReject}
            disabled={loading}
            className="rounded-lg border border-border px-4 py-2 font-semibold text-text-muted hover:border-red-400 hover:text-red-400 disabled:opacity-50"
          >
            Reject
          </button>
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
    </div>
  );
}
