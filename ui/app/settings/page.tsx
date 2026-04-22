"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getSettings,
  getHealth,
  updateFractalSettings,
  type SettingsResponse,
  type HealthResponse,
  type FractalSettings,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";

interface SliderRowProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  unit?: string;
  onChange: (v: number) => void;
}

function SliderRow({ label, value, min, max, step = 1, unit = "", onChange }: SliderRowProps) {
  return (
    <div className="flex items-center gap-4">
      <span className="text-text-muted w-44 shrink-0 text-sm">{label}</span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-border accent-accent"
      />
      <span className="font-mono text-sm w-16 text-right tabular-nums">
        {value}{unit}
      </span>
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === "ok"
      ? "bg-green-400"
      : status === "warn"
        ? "bg-yellow-400"
        : status === "fail"
          ? "bg-red-400"
          : "bg-gray-500";
  return <span className={`inline-block h-2.5 w-2.5 rounded-full ${color}`} />;
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [fractal, setFractal] = useState<FractalSettings | null>(null);
  const [fractalDirty, setFractalDirty] = useState(false);
  const [fractalSaving, setFractalSaving] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [s, h] = await Promise.all([getSettings(), getHealth()]);
      setSettings(s);
      setHealth(h);
      if (s.fractal) {
        setFractal(s.fractal);
        setFractalDirty(false);
      }
    } catch {
      /* API not reachable */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const updateFractalField = (field: keyof FractalSettings, value: number) => {
    setFractal((prev) => (prev ? { ...prev, [field]: value } : prev));
    setFractalDirty(true);
  };

  const saveFractal = async () => {
    if (!fractal) return;
    setFractalSaving(true);
    try {
      const res = await updateFractalSettings(fractal);
      setFractal(res.fractal);
      setFractalDirty(false);
    } catch {
      /* will show stale state */
    } finally {
      setFractalSaving(false);
    }
  };

  if (loading) {
    return <p className="text-text-muted py-12 text-center">Loading...</p>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="font-mono text-lg font-semibold">Settings</h1>
        <Button variant="outline" size="sm" onClick={refresh}>
          Refresh
        </Button>
      </div>

      {/* System Health */}
      <Card>
        <CardHeader className="p-3">
          <CardTitle>
            <span className="text-sm font-semibold uppercase tracking-wide text-text-muted">
              System Health
            </span>
            {health && (
              <span
                className={`ml-2 text-xs font-normal ${health.overall === "ok" ? "text-green-400" : "text-yellow-400"}`}
              >
                ({health.overall})
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {health ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {health.checks.map((c) => (
                <div
                  key={c.name}
                  className="flex items-center gap-2 rounded border border-border px-3 py-2"
                >
                  <StatusDot status={c.status} />
                  <span className="font-mono text-sm">{c.name}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-text-muted text-sm">Health check unavailable</p>
          )}
        </CardContent>
      </Card>

      {settings && (
        <>
          {/* General */}
          <Card>
            <CardHeader className="p-3">
              <CardTitle className="text-sm font-semibold uppercase tracking-wide text-text-muted">
                General
              </CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
                <dt className="text-text-muted">Version</dt>
                <dd className="font-mono">{settings.version}</dd>
                <dt className="text-text-muted">Environment</dt>
                <dd className="font-mono">{settings.environment}</dd>
                <dt className="text-text-muted">Planning Mode</dt>
                <dd className="font-mono">{settings.planning_mode}</dd>
                <dt className="text-text-muted">Execution Engine</dt>
                <dd className="font-mono">{settings.execution_engine}</dd>
                <dt className="text-text-muted">Local First</dt>
                <dd className="font-mono">{settings.local_first ? "Yes" : "No"}</dd>
              </dl>
            </CardContent>
          </Card>

          {/* Budget */}
          <Card>
            <CardHeader className="p-3">
              <CardTitle className="text-sm font-semibold uppercase tracking-wide text-text-muted">
                Budget
              </CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
                <dt className="text-text-muted">Monthly Budget</dt>
                <dd className="font-mono">${settings.budget.monthly_usd}</dd>
                <dt className="text-text-muted">Per-Task Budget</dt>
                <dd className="font-mono">${settings.budget.task_usd}</dd>
                <dt className="text-text-muted">Auto Downgrade</dt>
                <dd className="font-mono">
                  {settings.budget.auto_downgrade ? "Enabled" : "Disabled"}
                </dd>
              </dl>
            </CardContent>
          </Card>

          {/* Engines */}
          <Card>
            <CardHeader className="p-3">
              <CardTitle className="text-sm font-semibold uppercase tracking-wide text-text-muted">
                Engines
              </CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
                <dt className="text-text-muted">Default Engine</dt>
                <dd className="font-mono">{settings.engines.default_engine}</dd>
                <dt className="text-text-muted">Claude Code</dt>
                <dd className="font-mono">
                  {settings.engines.claude_code_enabled ? "Enabled" : "Disabled"}
                </dd>
                <dt className="text-text-muted">Gemini CLI</dt>
                <dd className="font-mono">
                  {settings.engines.gemini_cli_enabled ? "Enabled" : "Disabled"}
                </dd>
                <dt className="text-text-muted">Codex CLI</dt>
                <dd className="font-mono">
                  {settings.engines.codex_cli_enabled ? "Enabled" : "Disabled"}
                </dd>
                <dt className="text-text-muted">OpenHands URL</dt>
                <dd className="font-mono">{settings.engines.openhands_base_url}</dd>
                <dt className="text-text-muted">Ollama Model</dt>
                <dd className="font-mono">{settings.ollama.default_model}</dd>
              </dl>
            </CardContent>
          </Card>

          {/* API Keys */}
          <Card>
            <CardHeader className="p-3">
              <CardTitle className="text-sm font-semibold uppercase tracking-wide text-text-muted">
                API Keys
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex gap-4 text-sm">
                {Object.entries(settings.api_keys_configured).map(([k, v]) => (
                  <div key={k} className="flex items-center gap-2">
                    <StatusDot status={v ? "ok" : "fail"} />
                    <span className="font-mono capitalize">{k}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* LAEE / MCP */}
          <Card>
            <CardHeader className="p-3">
              <CardTitle className="text-sm font-semibold uppercase tracking-wide text-text-muted">
                Features
              </CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
                <dt className="text-text-muted">LAEE</dt>
                <dd className="font-mono">
                  {settings.laee.enabled ? "Enabled" : "Disabled"} (
                  {settings.laee.approval_mode})
                </dd>
                <dt className="text-text-muted">MCP</dt>
                <dd className="font-mono">
                  {settings.mcp.enabled ? "Enabled" : "Disabled"} (
                  {settings.mcp.transport})
                </dd>
              </dl>
            </CardContent>
          </Card>

          {/* Fractal Engine */}
          {fractal && (
            <Card>
              <CardHeader className="flex flex-row items-center justify-between p-3">
                <CardTitle className="text-sm font-semibold uppercase tracking-wide text-text-muted">
                  Fractal Engine
                </CardTitle>
                <Button
                  size="sm"
                  onClick={saveFractal}
                  disabled={!fractalDirty || fractalSaving}
                  className={
                    fractalDirty
                      ? "border-accent bg-accent/10 text-accent hover:bg-accent/20"
                      : "opacity-50"
                  }
                  variant="outline"
                >
                  {fractalSaving ? "Saving..." : "Save"}
                </Button>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <SliderRow
                    label="Max Depth"
                    value={fractal.max_depth}
                    min={1}
                    max={10}
                    onChange={(v) => updateFractalField("max_depth", v)}
                  />
                  <SliderRow
                    label="Candidates / Node"
                    value={fractal.candidates_per_node}
                    min={1}
                    max={10}
                    onChange={(v) => updateFractalField("candidates_per_node", v)}
                  />
                  <SliderRow
                    label="Max Concurrent Nodes"
                    value={fractal.max_concurrent_nodes}
                    min={0}
                    max={50}
                    unit={fractal.max_concurrent_nodes === 0 ? " (∞)" : ""}
                    onChange={(v) => updateFractalField("max_concurrent_nodes", v)}
                  />
                  <SliderRow
                    label="Throttle Delay"
                    value={fractal.throttle_delay_ms}
                    min={0}
                    max={10000}
                    step={100}
                    unit="ms"
                    onChange={(v) => updateFractalField("throttle_delay_ms", v)}
                  />
                  <SliderRow
                    label="Max Total Nodes"
                    value={fractal.max_total_nodes}
                    min={1}
                    max={100}
                    onChange={(v) => updateFractalField("max_total_nodes", v)}
                  />
                  <SliderRow
                    label="Max Reflection Rounds"
                    value={fractal.max_reflection_rounds}
                    min={0}
                    max={10}
                    onChange={(v) => updateFractalField("max_reflection_rounds", v)}
                  />
                </div>
                {fractalDirty && (
                  <p className="mt-3 text-xs text-text-muted">
                    Unsaved changes — applies to next task execution.
                  </p>
                )}
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
