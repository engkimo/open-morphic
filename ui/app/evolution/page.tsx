"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  getEvolutionStats,
  getFailurePatterns,
  getPreferences,
  triggerEvolution,
  type ExecutionStatsResponse,
  type FailurePattern,
  type ModelPreference,
  type EnginePreference,
  type EvolutionReportResponse,
} from "@/lib/api";
import StatsCard from "./components/StatsCard";
import FailureTable from "./components/FailureTable";
import PreferenceChart from "./components/PreferenceChart";
import EvolutionTimeline from "./components/EvolutionTimeline";

export default function EvolutionPage() {
  const [stats, setStats] = useState<ExecutionStatsResponse | null>(null);
  const [failures, setFailures] = useState<FailurePattern[]>([]);
  const [modelPrefs, setModelPrefs] = useState<ModelPreference[]>([]);
  const [enginePrefs, setEnginePrefs] = useState<EnginePreference[]>([]);
  const [reports, setReports] = useState<EvolutionReportResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [evolving, setEvolving] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [s, f, p] = await Promise.all([
        getEvolutionStats(),
        getFailurePatterns(),
        getPreferences(),
      ]);
      setStats(s);
      setFailures(f.patterns);
      setModelPrefs(p.model_preferences);
      setEnginePrefs(p.engine_preferences);
    } catch {
      /* backend may be down */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handleEvolve() {
    setEvolving(true);
    try {
      const report = await triggerEvolution();
      setReports((prev) => [report, ...prev]);
      await refresh();
    } catch {
      /* ignore */
    } finally {
      setEvolving(false);
    }
  }

  const rateColor =
    stats && stats.success_rate >= 0.8
      ? "text-success"
      : stats && stats.success_rate >= 0.5
        ? "text-warning"
        : "text-danger";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link
            href="/"
            className="text-sm text-text-muted hover:text-accent"
          >
            &larr; Dashboard
          </Link>
          <h2 className="font-mono text-lg font-bold tracking-tight">
            Evolution
          </h2>
        </div>
        <button
          onClick={handleEvolve}
          disabled={evolving}
          className="rounded-lg bg-accent px-4 py-1.5 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50"
        >
          {evolving ? "Evolving..." : "Run Evolution"}
        </button>
      </div>

      {loading && (
        <p className="py-8 text-center text-sm text-text-muted">Loading...</p>
      )}

      {!loading && stats && (
        <>
          {/* Stats Cards */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatsCard
              label="Total Tasks"
              value={stats.total_count.toLocaleString()}
            />
            <StatsCard
              label="Success Rate"
              value={`${(stats.success_rate * 100).toFixed(1)}%`}
              color={rateColor}
            />
            <StatsCard
              label="Avg Cost"
              value={`$${stats.avg_cost_usd.toFixed(4)}`}
              sub="per task"
            />
            <StatsCard
              label="Avg Duration"
              value={`${stats.avg_duration_seconds.toFixed(1)}s`}
              sub="per task"
            />
          </div>

          {/* Preference Charts */}
          <PreferenceChart
            modelPreferences={modelPrefs}
            enginePreferences={enginePrefs}
          />

          {/* Failure Table */}
          <div>
            <h3 className="mb-2 text-sm font-medium text-text-muted">
              Recent Failure Patterns
            </h3>
            <FailureTable patterns={failures} />
          </div>

          {/* Evolution Timeline */}
          <div>
            <h3 className="mb-2 text-sm font-medium text-text-muted">
              Evolution History
            </h3>
            <EvolutionTimeline reports={reports} />
          </div>
        </>
      )}

      {!loading && !stats && (
        <p className="py-8 text-center text-sm text-text-muted">
          Could not load evolution data. Is the backend running?
        </p>
      )}
    </div>
  );
}
