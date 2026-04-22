"use client";

import type { SharedTaskStateResponse } from "@/lib/api";

export default function StateDetail({
  state,
  onBack,
}: {
  state: SharedTaskStateResponse;
  onBack: () => void;
}) {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <button
          onClick={onBack}
          className="text-sm text-text-muted hover:text-accent"
        >
          Back
        </button>
        <h3 className="font-mono text-lg">Task: {state.task_id.slice(0, 12)}...</h3>
        {state.last_agent && (
          <span className="rounded bg-accent/20 px-2 py-0.5 text-xs text-accent">
            Last: {state.last_agent}
          </span>
        )}
        <span className="text-sm text-text-muted">
          Cost: ${state.total_cost_usd.toFixed(4)}
        </span>
      </div>

      {/* Decisions */}
      {state.decisions.length > 0 && (
        <div>
          <h4 className="mb-2 text-sm font-semibold text-text-muted">
            Decisions ({state.decisions.length})
          </h4>
          <div className="space-y-2">
            {state.decisions.map((d) => (
              <div
                key={d.id}
                className="rounded border border-border bg-surface p-3"
              >
                <div className="flex items-center justify-between text-xs text-text-muted">
                  <span className="font-mono">{d.agent_engine}</span>
                  <span>{(d.confidence * 100).toFixed(0)}% confidence</span>
                </div>
                <p className="mt-1 text-sm">{d.description}</p>
                {d.rationale && (
                  <p className="mt-1 text-xs text-text-muted">{d.rationale}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Artifacts */}
      {Object.keys(state.artifacts).length > 0 && (
        <div>
          <h4 className="mb-2 text-sm font-semibold text-text-muted">
            Artifacts ({Object.keys(state.artifacts).length})
          </h4>
          <div className="space-y-1">
            {Object.entries(state.artifacts).map(([k, v]) => (
              <div
                key={k}
                className="flex gap-2 rounded border border-border bg-surface p-2 text-sm"
              >
                <span className="font-mono text-accent">{k}:</span>
                <span className="truncate">{v}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Blockers */}
      {state.blockers.length > 0 && (
        <div>
          <h4 className="mb-2 text-sm font-semibold text-red-400">
            Blockers ({state.blockers.length})
          </h4>
          <ul className="list-disc pl-5 text-sm text-red-400">
            {state.blockers.map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Agent History */}
      {state.agent_history.length > 0 && (
        <div>
          <h4 className="mb-2 text-sm font-semibold text-text-muted">
            Agent History ({state.agent_history.length})
          </h4>
          <div className="space-y-1">
            {state.agent_history.map((a) => (
              <div
                key={a.id}
                className="flex items-center gap-3 rounded border border-border bg-surface p-2 text-sm"
              >
                <span className="font-mono text-xs text-accent">
                  {a.agent_engine}
                </span>
                <span className="rounded bg-border px-1.5 py-0.5 text-xs">
                  {a.action_type}
                </span>
                <span className="flex-1 truncate">{a.summary}</span>
                {a.cost_usd > 0 && (
                  <span className="text-xs text-text-muted">
                    ${a.cost_usd.toFixed(4)}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
