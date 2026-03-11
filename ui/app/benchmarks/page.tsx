"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { runBenchmarks, type BenchmarkResultResponse } from "@/lib/api";

function ScoreBar({ score, label }: { score: number; label: string }) {
  const pct = Math.round(score * 100);
  const color =
    score >= 0.85
      ? "bg-success"
      : score >= 0.5
        ? "bg-warning"
        : "bg-danger";
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-sm">
        <span className="text-text-muted">{label}</span>
        <span className="font-mono font-bold">{pct}%</span>
      </div>
      <div className="h-2 w-full rounded-full bg-border">
        <div
          className={`h-2 rounded-full ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export default function BenchmarksPage() {
  const [result, setResult] = useState<BenchmarkResultResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const handleRun = useCallback(async () => {
    setLoading(true);
    try {
      const data = await runBenchmarks();
      setResult(data);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href="/" className="text-sm text-text-muted hover:text-accent">
            &larr; Dashboard
          </Link>
          <h1 className="text-xl font-bold">UCL Benchmarks</h1>
        </div>
        <button
          onClick={handleRun}
          disabled={loading}
          className="rounded bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent/80 disabled:opacity-50"
        >
          {loading ? "Running..." : "Run Benchmarks"}
        </button>
      </div>

      {!result && !loading && (
        <p className="text-sm text-text-muted">
          Click &quot;Run Benchmarks&quot; to measure context continuity and memory dedup accuracy.
        </p>
      )}

      {result && (
        <>
          {/* Overall Score */}
          <div className="rounded-lg border border-border bg-surface p-6">
            <h2 className="mb-4 text-lg font-bold">Overall Score</h2>
            <ScoreBar score={result.overall_score} label="Combined" />
            {result.overall_score >= 0.85 ? (
              <p className="mt-2 text-sm text-success">
                Benchmark threshold (85%) passed
              </p>
            ) : (
              <p className="mt-2 text-sm text-warning">
                Below 85% threshold
              </p>
            )}
          </div>

          {/* Context Continuity */}
          {result.context_continuity && (
            <div className="rounded-lg border border-border bg-surface p-6">
              <h2 className="mb-4 text-lg font-bold">Context Continuity</h2>
              <ScoreBar
                score={result.context_continuity.overall_score}
                label="Average"
              />
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-text-muted">
                      <th className="pb-2 pr-4">Engine</th>
                      <th className="pb-2 pr-4 text-right">Score</th>
                      <th className="pb-2 pr-4 text-right">Decisions</th>
                      <th className="pb-2 pr-4 text-right">Artifacts</th>
                      <th className="pb-2 pr-4 text-right">Blockers</th>
                      <th className="pb-2 text-right">Length</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.context_continuity.adapter_scores.map((s) => (
                      <tr key={s.engine} className="border-b border-border/50">
                        <td className="py-2 pr-4 font-mono text-accent">
                          {s.engine}
                        </td>
                        <td className="py-2 pr-4 text-right font-mono">
                          <span
                            className={
                              s.score >= 0.85
                                ? "text-success"
                                : s.score >= 0.5
                                  ? "text-warning"
                                  : "text-danger"
                            }
                          >
                            {Math.round(s.score * 100)}%
                          </span>
                        </td>
                        <td className="py-2 pr-4 text-right">
                          {s.decisions_found}/{s.decisions_injected}
                        </td>
                        <td className="py-2 pr-4 text-right">
                          {s.artifacts_found}/{s.artifacts_injected}
                        </td>
                        <td className="py-2 pr-4 text-right">
                          {s.blockers_found}/{s.blockers_injected}
                        </td>
                        <td className="py-2 text-right font-mono text-text-muted">
                          {s.context_length}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Dedup Accuracy */}
          {result.dedup_accuracy && (
            <div className="rounded-lg border border-border bg-surface p-6">
              <h2 className="mb-4 text-lg font-bold">
                Memory Deduplication
              </h2>
              <ScoreBar
                score={result.dedup_accuracy.overall_accuracy}
                label="Accuracy"
              />
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-text-muted">
                      <th className="pb-2 pr-4">Scenario</th>
                      <th className="pb-2 pr-4 text-right">Dedup Rate</th>
                      <th className="pb-2 pr-4 text-right">Raw</th>
                      <th className="pb-2 text-right">Unique</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.dedup_accuracy.scores.map((s) => (
                      <tr
                        key={s.scenario}
                        className="border-b border-border/50"
                      >
                        <td className="py-2 pr-4 font-mono text-accent">
                          {s.scenario}
                        </td>
                        <td className="py-2 pr-4 text-right font-mono">
                          <span
                            className={
                              s.dedup_rate >= 0.5
                                ? "text-success"
                                : "text-warning"
                            }
                          >
                            {Math.round(s.dedup_rate * 100)}%
                          </span>
                        </td>
                        <td className="py-2 pr-4 text-right">
                          {s.total_raw}
                        </td>
                        <td className="py-2 text-right">{s.deduped_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Errors */}
          {result.errors.length > 0 && (
            <div className="rounded-lg border border-danger/50 bg-surface p-4">
              <h3 className="mb-2 text-sm font-medium text-danger">Errors</h3>
              {result.errors.map((err, i) => (
                <p key={i} className="text-sm text-text-muted">
                  {err}
                </p>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
