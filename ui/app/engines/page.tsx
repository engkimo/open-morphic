"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  listEngines,
  runEngine,
  listTasks,
  type EngineInfoResponse,
  type EngineRunResponse,
} from "@/lib/api";
import { useAutoRefresh } from "@/lib/useAutoRefresh";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const ENGINE_LABELS: Record<string, string> = {
  ollama: "Ollama (Local)",
  claude_code: "Claude Code SDK",
  gemini_cli: "Gemini CLI + ADK",
  codex_cli: "OpenAI Codex CLI",
  openhands: "OpenHands",
  direct_llm: "Direct LLM",
};

function CapBadge({
  label,
  active,
}: {
  label: string;
  active: boolean;
}) {
  return (
    <Badge
      variant={active ? "info" : "outline"}
      className={!active ? "bg-border text-text-muted" : ""}
    >
      {label}
    </Badge>
  );
}

function EngineCard({ engine }: { engine: EngineInfoResponse }) {
  const label = ENGINE_LABELS[engine.engine_type] || engine.engine_type;
  const isLocal = engine.cost_per_hour_usd === 0;

  return (
    <Card className="transition-colors hover:border-accent">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span
              className={`h-2.5 w-2.5 rounded-full ${
                engine.available ? "bg-success" : "bg-danger"
              }`}
            />
            <span className="font-mono text-sm font-semibold">{label}</span>
          </div>
          <div className="flex items-center gap-1.5">
            {isLocal && (
              <Badge variant="free">FREE</Badge>
            )}
            <span
              className={`text-xs ${
                engine.available ? "text-success" : "text-danger"
              }`}
            >
              {engine.available ? "Online" : "Offline"}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs mb-3">
          <div>
            <span className="text-text-muted">Context</span>
            <div className="font-mono">
              {engine.max_context_tokens >= 1_000_000
                ? `${(engine.max_context_tokens / 1_000_000).toFixed(1)}M`
                : `${(engine.max_context_tokens / 1_000).toFixed(0)}K`}{" "}
              tokens
            </div>
          </div>
          <div>
            <span className="text-text-muted">Cost</span>
            <div className="font-mono">
              {isLocal ? "$0.00" : `$${engine.cost_per_hour_usd.toFixed(2)}`}/hr
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-1.5">
          <CapBadge label="Sandbox" active={engine.supports_sandbox} />
          <CapBadge label="Parallel" active={engine.supports_parallel} />
          <CapBadge label="MCP" active={engine.supports_mcp} />
        </div>
      </CardContent>
    </Card>
  );
}

export default function EnginesPage() {
  const [engines, setEngines] = useState<EngineInfoResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [runResult, setRunResult] = useState<EngineRunResponse | null>(null);
  const [runLoading, setRunLoading] = useState(false);
  const [task, setTask] = useState("");
  const [selectedEngine, setSelectedEngine] = useState("");
  const [hasActive, setHasActive] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [data, taskData] = await Promise.all([
        listEngines(),
        listTasks(),
      ]);
      setEngines(data.engines);
      setHasActive(
        taskData.tasks.some(
          (t) => t.status === "running" || t.status === "pending",
        ),
      );
    } catch {
      /* backend may be down */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // TD-170: Auto-refresh when tasks are running/pending
  useAutoRefresh(refresh, hasActive);

  async function handleRun(e: React.FormEvent) {
    e.preventDefault();
    if (!task.trim()) return;
    setRunLoading(true);
    setRunResult(null);
    try {
      const result = await runEngine({
        task: task.trim(),
        engine: selectedEngine || undefined,
      });
      setRunResult(result);
    } catch {
      /* ignore */
    } finally {
      setRunLoading(false);
    }
  }

  const available = engines.filter((e) => e.available).length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/" className="text-sm text-text-muted hover:text-accent">
            &larr; Dashboard
          </Link>
          <h1 className="font-mono text-lg font-semibold tracking-tight">
            Engine Status
          </h1>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={refresh}
          disabled={loading}
        >
          {loading ? "Loading..." : "Refresh"}
        </Button>
      </div>

      {/* Summary */}
      <div className="flex items-center gap-6 text-sm">
        <div>
          <span className="text-text-muted">Engines: </span>
          <span className="font-mono font-bold">
            {available}/{engines.length}
          </span>
          <span className="text-text-muted"> online</span>
        </div>
        <div>
          <span className="text-text-muted">Local: </span>
          <span className="font-mono font-bold text-local-free">
            {engines.filter((e) => e.cost_per_hour_usd === 0 && e.available).length}
          </span>
        </div>
      </div>

      {/* Engine Grid */}
      {loading ? (
        <p className="py-8 text-center text-sm text-text-muted">Loading...</p>
      ) : engines.length === 0 ? (
        <p className="py-8 text-center text-sm text-text-muted">
          No engines registered. Is the backend running?
        </p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {engines.map((engine) => (
            <EngineCard key={engine.engine_type} engine={engine} />
          ))}
        </div>
      )}

      {/* Run Task */}
      <Card>
        <CardHeader className="p-3">
          <CardTitle className="text-sm font-semibold uppercase tracking-wide text-text-muted">
            Run Task on Engine
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleRun} className="space-y-3">
            <div className="flex gap-3">
              <Input
                type="text"
                value={task}
                onChange={(e) => setTask(e.target.value)}
                placeholder="Describe task..."
                disabled={runLoading}
                className="flex-1"
              />
              <select
                value={selectedEngine}
                onChange={(e) => setSelectedEngine(e.target.value)}
                className="rounded-md border border-input bg-transparent px-3 py-1 font-mono text-sm text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                <option value="">Auto-route</option>
                {engines
                  .filter((e) => e.available)
                  .map((e) => (
                    <option key={e.engine_type} value={e.engine_type}>
                      {ENGINE_LABELS[e.engine_type] || e.engine_type}
                    </option>
                  ))}
              </select>
              <Button
                type="submit"
                size="sm"
                disabled={runLoading || !task.trim()}
              >
                {runLoading ? "Running..." : "Run"}
              </Button>
            </div>
          </form>

          {runResult && (
            <div className="mt-4 space-y-2">
              <div className="flex items-center gap-4 text-sm">
                <span
                  className={`font-mono font-bold ${
                    runResult.success ? "text-success" : "text-danger"
                  }`}
                >
                  {runResult.success ? "Success" : "Failed"}
                </span>
                <span className="text-text-muted">
                  Engine: {ENGINE_LABELS[runResult.engine] || runResult.engine}
                </span>
                {runResult.model_used && (
                  <span className="text-text-muted">
                    Model: {runResult.model_used}
                  </span>
                )}
                <span className="text-text-muted">
                  ${runResult.cost_usd.toFixed(4)} / {runResult.duration_seconds.toFixed(1)}s
                </span>
              </div>
              {runResult.engines_tried.length > 1 && (
                <div className="text-xs text-text-muted">
                  Tried: {runResult.engines_tried.join(" → ")}
                </div>
              )}
              {runResult.fallback_reason && (
                <div className="text-xs text-warning">
                  Fallback: {runResult.fallback_reason}
                </div>
              )}
              <div className="rounded border border-border bg-background p-3">
                <pre className="whitespace-pre-wrap font-mono text-xs text-foreground">
                  {runResult.output}
                </pre>
              </div>
              {runResult.error && (
                <div className="rounded border border-danger/30 bg-danger/10 p-2 text-xs text-danger">
                  {runResult.error}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
