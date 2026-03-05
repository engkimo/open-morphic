"use client";

import type { EvolutionReportResponse } from "@/lib/api";

interface EvolutionTimelineProps {
  reports: EvolutionReportResponse[];
}

export default function EvolutionTimeline({ reports }: EvolutionTimelineProps) {
  if (reports.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-text-muted">
        No evolution runs yet. Click &quot;Run Evolution&quot; to start.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {reports.map((r, i) => (
        <div
          key={i}
          className="rounded-lg border border-border bg-surface p-3"
        >
          <div className="flex items-center justify-between">
            <span className="rounded bg-accent/20 px-2 py-0.5 text-xs font-medium text-accent">
              {r.level}
            </span>
            <span className="text-xs text-text-muted">
              {new Date(r.created_at).toLocaleString()}
            </span>
          </div>
          <p className="mt-2 text-sm">{r.summary}</p>
          <div className="mt-2 flex gap-4 text-xs text-text-muted">
            {r.strategy_update && (
              <>
                <span>
                  Models: {r.strategy_update.model_preferences_updated}
                </span>
                <span>
                  Engines: {r.strategy_update.engine_preferences_updated}
                </span>
                <span>Rules: {r.strategy_update.recovery_rules_added}</span>
              </>
            )}
            <span>Gaps: {r.tool_gaps_found}</span>
          </div>
          {r.tools_suggested.length > 0 && (
            <p className="mt-1 text-xs text-warning">
              Suggested: {r.tools_suggested.join(", ")}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
