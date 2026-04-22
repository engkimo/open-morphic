"use client";

import type { FailurePattern } from "@/lib/api";

interface FailureTableProps {
  patterns: FailurePattern[];
}

export default function FailureTable({ patterns }: FailureTableProps) {
  if (patterns.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-text-muted">
        No failure patterns detected.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-border bg-surface">
          <tr>
            <th className="px-4 py-2 font-medium text-text-muted">Error</th>
            <th className="px-4 py-2 font-medium text-text-muted text-right">
              Count
            </th>
            <th className="px-4 py-2 font-medium text-text-muted">
              Task Types
            </th>
            <th className="px-4 py-2 font-medium text-text-muted">Engines</th>
          </tr>
        </thead>
        <tbody>
          {patterns.map((p, i) => (
            <tr key={i} className="border-b border-border last:border-0">
              <td className="px-4 py-2 font-mono text-xs">
                {p.error_pattern.slice(0, 60)}
              </td>
              <td className="px-4 py-2 text-right text-danger font-bold">
                {p.count}
              </td>
              <td className="px-4 py-2 text-xs text-text-muted">
                {p.task_types.join(", ")}
              </td>
              <td className="px-4 py-2 text-xs text-text-muted">
                {p.engines.join(", ")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
