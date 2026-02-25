"use client";

import type { TaskResponse } from "@/lib/api";

const STATUS_DOT: Record<string, string> = {
  pending: "bg-text-muted",
  running: "bg-info animate-pulse",
  success: "bg-success",
  failed: "bg-danger",
};

interface TaskDetailProps {
  task: TaskResponse;
}

export default function TaskDetail({ task }: TaskDetailProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-mono text-xl font-semibold">{task.goal}</h2>
        <span className="rounded border border-border px-3 py-1 text-xs text-text-muted">
          {task.status}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-4 text-center text-sm">
        <div className="rounded-lg border border-border bg-surface p-3">
          <div className="text-2xl font-bold text-accent">
            {Math.round(task.success_rate * 100)}%
          </div>
          <div className="text-text-muted">Success</div>
        </div>
        <div className="rounded-lg border border-border bg-surface p-3">
          <div className="text-2xl font-bold">{task.subtasks.length}</div>
          <div className="text-text-muted">Subtasks</div>
        </div>
        <div className="rounded-lg border border-border bg-surface p-3">
          <div className="text-2xl font-bold text-local-free">
            ${task.total_cost_usd.toFixed(4)}
          </div>
          <div className="text-text-muted">Cost</div>
        </div>
      </div>

      <div className="space-y-2">
        <h3 className="font-mono text-sm font-semibold text-text-muted">
          Subtasks
        </h3>
        {task.subtasks.map((st) => (
          <div
            key={st.id}
            className="flex items-start gap-3 rounded-lg border border-border bg-surface px-4 py-3"
          >
            <span
              className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${STATUS_DOT[st.status] ?? "bg-text-muted"}`}
            />
            <div className="flex-1">
              <div className="font-mono text-sm">{st.description}</div>
              {st.result && (
                <div className="mt-1 text-xs text-text-muted">{st.result}</div>
              )}
              {st.error && (
                <div className="mt-1 text-xs text-danger">{st.error}</div>
              )}
            </div>
            {st.model_used && (
              <span className="text-xs text-text-muted">{st.model_used}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
