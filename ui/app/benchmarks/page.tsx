"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { runBenchmarks, type BenchmarkResultResponse } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

function ScoreBar({ score, label }: { score: number; label: string }) {
  const pct = Math.round(score * 100);
  const indicatorColor =
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
      <Progress value={pct} indicatorClassName={indicatorColor} />
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
          <Button variant="link" size="sm" asChild>
            <Link href="/">&larr; Dashboard</Link>
          </Button>
          <h1 className="text-lg font-semibold">UCL Benchmarks</h1>
        </div>
        <Button onClick={handleRun} disabled={loading}>
          {loading ? "Running..." : "Run Benchmarks"}
        </Button>
      </div>

      {!result && !loading && (
        <p className="text-sm text-text-muted">
          Click &quot;Run Benchmarks&quot; to measure context continuity and memory dedup accuracy.
        </p>
      )}

      {result && (
        <>
          {/* Overall Score */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Overall Score</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <ScoreBar score={result.overall_score} label="Combined" />
              {result.overall_score >= 0.85 ? (
                <p className="text-sm text-success">
                  Benchmark threshold (85%) passed
                </p>
              ) : (
                <p className="text-sm text-warning">
                  Below 85% threshold
                </p>
              )}
            </CardContent>
          </Card>

          {/* Context Continuity */}
          {result.context_continuity && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Context Continuity</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <ScoreBar
                  score={result.context_continuity.overall_score}
                  label="Average"
                />
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Engine</TableHead>
                      <TableHead className="text-right">Score</TableHead>
                      <TableHead className="text-right">Decisions</TableHead>
                      <TableHead className="text-right">Artifacts</TableHead>
                      <TableHead className="text-right">Blockers</TableHead>
                      <TableHead className="text-right">Length</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {result.context_continuity.adapter_scores.map((s) => (
                      <TableRow key={s.engine}>
                        <TableCell className="font-mono text-accent">
                          {s.engine}
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          <span
                            className={cn(
                              s.score >= 0.85
                                ? "text-success"
                                : s.score >= 0.5
                                  ? "text-warning"
                                  : "text-danger",
                            )}
                          >
                            {Math.round(s.score * 100)}%
                          </span>
                        </TableCell>
                        <TableCell className="text-right">
                          {s.decisions_found}/{s.decisions_injected}
                        </TableCell>
                        <TableCell className="text-right">
                          {s.artifacts_found}/{s.artifacts_injected}
                        </TableCell>
                        <TableCell className="text-right">
                          {s.blockers_found}/{s.blockers_injected}
                        </TableCell>
                        <TableCell className="text-right font-mono text-text-muted">
                          {s.context_length}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}

          {/* Dedup Accuracy */}
          {result.dedup_accuracy && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  Memory Deduplication
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <ScoreBar
                  score={result.dedup_accuracy.overall_accuracy}
                  label="Accuracy"
                />
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Scenario</TableHead>
                      <TableHead className="text-right">Dedup Rate</TableHead>
                      <TableHead className="text-right">Raw</TableHead>
                      <TableHead className="text-right">Unique</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {result.dedup_accuracy.scores.map((s) => (
                      <TableRow key={s.scenario}>
                        <TableCell className="font-mono text-accent">
                          {s.scenario}
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          <span
                            className={cn(
                              s.dedup_rate >= 0.5
                                ? "text-success"
                                : "text-warning",
                            )}
                          >
                            {Math.round(s.dedup_rate * 100)}%
                          </span>
                        </TableCell>
                        <TableCell className="text-right">
                          {s.total_raw}
                        </TableCell>
                        <TableCell className="text-right">{s.deduped_count}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}

          {/* Errors */}
          {result.errors.length > 0 && (
            <Card className="border-destructive/50">
              <CardHeader>
                <CardTitle className="text-sm text-destructive">Errors</CardTitle>
              </CardHeader>
              <CardContent>
                {result.errors.map((err, i) => (
                  <p key={i} className="text-sm text-text-muted">
                    {err}
                  </p>
                ))}
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
