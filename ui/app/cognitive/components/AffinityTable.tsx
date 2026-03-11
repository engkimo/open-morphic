"use client";

import type { AffinityScoreResponse } from "@/lib/api";

export default function AffinityTable({
  scores,
}: {
  scores: AffinityScoreResponse[];
}) {
  if (scores.length === 0) {
    return <p className="text-sm text-text-muted">No affinity scores recorded.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-text-muted">
            <th className="pb-2 pr-4">Engine</th>
            <th className="pb-2 pr-4">Topic</th>
            <th className="pb-2 pr-4 text-right">Score</th>
            <th className="pb-2 pr-4 text-right">Success</th>
            <th className="pb-2 text-right">Samples</th>
          </tr>
        </thead>
        <tbody>
          {scores.map((s, i) => (
            <tr key={i} className="border-b border-border/50">
              <td className="py-2 pr-4 font-mono">{s.engine}</td>
              <td className="py-2 pr-4">{s.topic}</td>
              <td className="py-2 pr-4 text-right">
                <span
                  className={
                    s.score >= 0.7
                      ? "text-green-400"
                      : s.score >= 0.4
                        ? "text-yellow-400"
                        : "text-red-400"
                  }
                >
                  {s.score.toFixed(2)}
                </span>
              </td>
              <td className="py-2 pr-4 text-right">
                {(s.success_rate * 100).toFixed(0)}%
              </td>
              <td className="py-2 text-right">{s.sample_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
