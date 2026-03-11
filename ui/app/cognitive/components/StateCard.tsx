"use client";

import type { SharedTaskStateResponse } from "@/lib/api";

export default function StateCard({
  state,
  onSelect,
}: {
  state: SharedTaskStateResponse;
  onSelect: (id: string) => void;
}) {
  const blockerCount = state.blockers.length;

  return (
    <button
      onClick={() => onSelect(state.task_id)}
      className="w-full rounded-lg border border-border bg-surface p-4 text-left hover:border-accent transition-colors"
    >
      <div className="flex items-center justify-between mb-2">
        <span className="font-mono text-sm text-text-muted truncate max-w-[200px]">
          {state.task_id.slice(0, 8)}...
        </span>
        {state.last_agent && (
          <span className="rounded bg-accent/20 px-2 py-0.5 text-xs text-accent">
            {state.last_agent}
          </span>
        )}
      </div>

      <div className="flex gap-4 text-xs text-text-muted">
        <span>{state.decisions.length} decisions</span>
        <span>{Object.keys(state.artifacts).length} artifacts</span>
        {blockerCount > 0 && (
          <span className="text-red-400">{blockerCount} blockers</span>
        )}
      </div>

      <div className="mt-2 flex items-center justify-between text-xs text-text-muted">
        <span>${state.total_cost_usd.toFixed(4)}</span>
        <span>{new Date(state.updated_at).toLocaleString()}</span>
      </div>
    </button>
  );
}
