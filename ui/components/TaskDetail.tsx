"use client";

import type { TaskResponse } from "@/lib/api";
import { parseResult } from "@/lib/resultParser";
import CodeBlock from "./CodeBlock";
import ExecutionResult from "./ExecutionResult";

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
        {task.subtasks.map((st) => {
          const parsed = parseResult(st.result);
          const hasCode = st.code != null;

          return (
            <div
              key={st.id}
              className="rounded-lg border border-border bg-surface px-4 py-3"
            >
              <div className="flex items-start gap-3">
                <span
                  className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${STATUS_DOT[st.status] ?? "bg-text-muted"}`}
                />
                <div className="flex-1 min-w-0">
                  <div className="font-mono text-sm">{st.description}</div>
                </div>
                {st.model_used && (
                  <span className="text-xs text-text-muted shrink-0">
                    {st.model_used}
                  </span>
                )}
              </div>

              {/* Code execution result */}
              {hasCode && (
                <div className="mt-3">
                  <ExecutionResult
                    code={st.code!}
                    output={st.execution_output}
                    success={st.status === "success"}
                  />
                </div>
              )}

              {/* Non-code result: JSON or plain text */}
              {!hasCode && st.result && (
                <div className="mt-2">
                  {parsed.type === "json" || parsed.type === "code" ? (
                    <CodeBlock
                      code={parsed.content}
                      language={parsed.language}
                    />
                  ) : (
                    <div className="text-xs text-text-muted">{parsed.content}</div>
                  )}
                </div>
              )}

              {/* Error display */}
              {st.error && (
                <div className="mt-2 rounded border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
                  {st.error}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
