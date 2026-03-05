"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  getModelStatus,
  pullModel,
  deleteModel,
  switchModel,
  getRunningModels,
  type ModelStatus as ModelStatusType,
} from "@/lib/api";

export default function ModelsPage() {
  const [status, setStatus] = useState<ModelStatusType | null>(null);
  const [running, setRunning] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pullName, setPullName] = useState("");
  const [pulling, setPulling] = useState(false);
  const [confirm, setConfirm] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [s, r] = await Promise.all([getModelStatus(), getRunningModels()]);
      setStatus(s);
      setRunning(r);
    } catch {
      /* backend may be down */
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handlePull(e: React.FormEvent) {
    e.preventDefault();
    const name = pullName.trim();
    if (!name) return;
    setPulling(true);
    setError(null);
    try {
      await pullModel(name);
      setPullName("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pull failed");
    } finally {
      setPulling(false);
    }
  }

  async function handleDelete(name: string) {
    if (confirm !== name) {
      setConfirm(name);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await deleteModel(name);
      setConfirm(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleSwitch(name: string) {
    setLoading(true);
    setError(null);
    try {
      await switchModel(name);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Switch failed");
    } finally {
      setLoading(false);
    }
  }

  const runningNames = new Set(
    running.map((r) => String(r.name ?? "")).filter(Boolean),
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link
          href="/"
          className="text-sm text-text-muted hover:text-accent"
        >
          &larr; Dashboard
        </Link>
        <h2 className="font-mono text-lg font-bold tracking-tight">
          Model Management
        </h2>
      </div>

      {/* Ollama status */}
      <div className="rounded-lg border border-border bg-surface p-4">
        <h3 className="mb-3 font-mono text-sm font-semibold text-text-muted">
          Ollama Status
        </h3>
        {status ? (
          <div className="flex items-center gap-4 text-sm">
            <div className="flex items-center gap-2">
              <span
                className={`h-2 w-2 rounded-full ${
                  status.ollama_running ? "bg-success" : "bg-danger"
                }`}
              />
              <span>
                {status.ollama_running ? "Running" : "Stopped"}
              </span>
            </div>
            <span className="text-text-muted">
              Default: {status.default_model}
            </span>
          </div>
        ) : (
          <p className="text-sm text-text-muted">Loading...</p>
        )}
      </div>

      {/* Pull new model */}
      <div className="rounded-lg border border-border bg-surface p-4">
        <h3 className="mb-3 font-mono text-sm font-semibold text-text-muted">
          Pull Model
        </h3>
        <form onSubmit={handlePull} className="flex gap-3">
          <input
            type="text"
            value={pullName}
            onChange={(e) => setPullName(e.target.value)}
            placeholder="e.g. qwen3:8b, phi4:14b"
            disabled={pulling}
            className="flex-1 rounded-lg border border-border bg-background px-4 py-2 font-mono text-sm text-foreground placeholder:text-text-muted focus:border-accent focus:outline-none"
          />
          <button
            type="submit"
            disabled={pulling || !pullName.trim()}
            className="rounded-lg bg-accent px-4 py-2 font-mono text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            {pulling ? "Pulling..." : "Pull"}
          </button>
        </form>
      </div>

      {error && <p className="text-sm text-danger">{error}</p>}

      {/* Model list */}
      <div className="space-y-2">
        <h3 className="font-mono text-sm font-semibold text-text-muted">
          Available Models
        </h3>
        {!status || status.models.length === 0 ? (
          <p className="py-8 text-center text-sm text-text-muted">
            No models available. Pull a model to get started.
          </p>
        ) : (
          status.models.map((model) => {
            const isDefault = model.name === status.default_model;
            const isRunning = runningNames.has(model.name);
            return (
              <div
                key={model.name}
                className="flex items-center justify-between rounded-lg border border-border bg-surface px-4 py-3 transition-colors hover:border-accent"
              >
                <div className="flex items-center gap-3">
                  <span
                    className={`h-2 w-2 rounded-full ${
                      model.available ? "bg-success" : "bg-danger"
                    }`}
                  />
                  <span className="font-mono text-sm">{model.name}</span>
                  {isDefault && (
                    <span className="rounded bg-accent/20 px-1.5 py-0.5 text-[10px] font-bold text-accent">
                      DEFAULT
                    </span>
                  )}
                  {isRunning && (
                    <span className="rounded bg-info/20 px-1.5 py-0.5 text-[10px] font-bold text-info">
                      RUNNING
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {!isDefault && (
                    <button
                      onClick={() => handleSwitch(model.name)}
                      disabled={loading}
                      className="rounded px-3 py-1.5 font-mono text-xs font-semibold text-accent transition-opacity hover:opacity-90 disabled:opacity-40"
                    >
                      Set Default
                    </button>
                  )}
                  <button
                    onClick={() => handleDelete(model.name)}
                    disabled={loading}
                    className={`rounded px-3 py-1.5 font-mono text-xs font-semibold transition-opacity hover:opacity-90 disabled:opacity-40 ${
                      confirm === model.name
                        ? "bg-danger/20 text-danger"
                        : "text-text-muted"
                    }`}
                  >
                    {confirm === model.name ? "Confirm?" : "Delete"}
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
