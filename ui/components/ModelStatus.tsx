"use client";

import type { ModelStatus as ModelStatusType } from "@/lib/api";

interface ModelStatusProps {
  status: ModelStatusType | null;
}

export default function ModelStatus({ status }: ModelStatusProps) {
  if (!status) return null;

  return (
    <div className="rounded-lg border border-border bg-surface p-4 text-sm">
      <h3 className="mb-3 font-mono font-semibold text-text-muted">Models</h3>
      <div className="flex items-center gap-2 mb-3">
        <span
          className={`h-2 w-2 rounded-full ${status.ollama_running ? "bg-success" : "bg-danger"}`}
        />
        <span className="text-text-muted">
          Ollama {status.ollama_running ? "Online" : "Offline"}
        </span>
      </div>
      {status.models.length > 0 && (
        <div className="space-y-1">
          {status.models.map((m) => (
            <div
              key={m.name}
              className="flex items-center justify-between text-xs"
            >
              <span className="font-mono">{m.name}</span>
              {m.name === status.default_model && (
                <span className="rounded bg-accent/20 px-1.5 py-0.5 text-accent">
                  default
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
