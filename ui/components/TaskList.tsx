"use client";

import Link from "next/link";
import type { TaskResponse } from "@/lib/api";

const STATUS_ICON: Record<string, string> = {
  pending: "\u23F3",
  running: "\u26A1",
  success: "\u2713",
  failed: "\u2717",
  fallback: "\u21BB",
};

const STATUS_COLOR: Record<string, string> = {
  pending: "text-text-muted",
  running: "text-info",
  success: "text-success",
  failed: "text-danger",
  fallback: "text-warning",
};

interface TaskListProps {
  tasks: TaskResponse[];
}

export default function TaskList({ tasks }: TaskListProps) {
  if (tasks.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-text-muted">
        No tasks yet. Enter a goal above to get started.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {tasks.map((task) => (
        <Link
          key={task.id}
          href={`/tasks/${task.id}`}
          className="flex items-center justify-between rounded-lg border border-border bg-surface px-4 py-3 transition-colors hover:border-accent"
        >
          <div className="flex items-center gap-3">
            <span className={`text-lg ${STATUS_COLOR[task.status] ?? ""}`}>
              {STATUS_ICON[task.status] ?? "?"}
            </span>
            <span className="font-mono text-sm">{task.goal}</span>
          </div>
          <div className="flex items-center gap-4 text-xs text-text-muted">
            <span>
              {(task.subtasks ?? []).length} subtask{(task.subtasks ?? []).length !== 1 && "s"}
            </span>
            {(task.total_cost_usd ?? 0) === 0 ? (
              <span className="rounded bg-local-free/20 px-2 py-0.5 text-local-free">
                FREE
              </span>
            ) : (
              <span>${(task.total_cost_usd ?? 0).toFixed(4)}</span>
            )}
          </div>
        </Link>
      ))}
    </div>
  );
}
