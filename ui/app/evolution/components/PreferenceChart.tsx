"use client";

import type { EnginePreference, ModelPreference } from "@/lib/api";

interface PreferenceChartProps {
  modelPreferences: ModelPreference[];
  enginePreferences: EnginePreference[];
}

function Bar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const width = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <span className="w-36 truncate text-xs text-text-muted">{label}</span>
      <div className="flex-1 rounded-full bg-border h-4">
        <div
          className={`h-4 rounded-full ${color}`}
          style={{ width: `${width}%` }}
        />
      </div>
      <span className="w-12 text-right text-xs font-mono">
        {(value * 100).toFixed(0)}%
      </span>
    </div>
  );
}

export default function PreferenceChart({
  modelPreferences,
  enginePreferences,
}: PreferenceChartProps) {
  return (
    <div className="grid gap-6 md:grid-cols-2">
      <div className="rounded-lg border border-border bg-surface p-4">
        <h3 className="mb-3 text-sm font-medium text-text-muted">
          Model Preferences (by success rate)
        </h3>
        {modelPreferences.length === 0 ? (
          <p className="text-xs text-text-muted">
            No data yet. Run tasks to build preferences.
          </p>
        ) : (
          <div className="space-y-2">
            {modelPreferences
              .sort((a, b) => b.success_rate - a.success_rate)
              .slice(0, 8)
              .map((p) => (
                <Bar
                  key={`${p.task_type}-${p.model}`}
                  label={`${p.model} (${p.task_type})`}
                  value={p.success_rate}
                  max={1}
                  color="bg-accent"
                />
              ))}
          </div>
        )}
      </div>

      <div className="rounded-lg border border-border bg-surface p-4">
        <h3 className="mb-3 text-sm font-medium text-text-muted">
          Engine Preferences (by success rate)
        </h3>
        {enginePreferences.length === 0 ? (
          <p className="text-xs text-text-muted">
            No data yet. Run tasks to build preferences.
          </p>
        ) : (
          <div className="space-y-2">
            {enginePreferences
              .sort((a, b) => b.success_rate - a.success_rate)
              .slice(0, 8)
              .map((p) => (
                <Bar
                  key={`${p.task_type}-${p.engine}`}
                  label={`${p.engine} (${p.task_type})`}
                  value={p.success_rate}
                  max={1}
                  color="bg-success"
                />
              ))}
          </div>
        )}
      </div>
    </div>
  );
}
