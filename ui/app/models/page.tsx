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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

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
        <Button variant="link" size="sm" asChild>
          <Link href="/">&larr; Dashboard</Link>
        </Button>
        <h2 className="font-mono text-lg font-semibold tracking-tight">
          Model Management
        </h2>
      </div>

      {/* Ollama status */}
      <Card>
        <CardHeader>
          <CardTitle className="text-text-muted">Ollama Status</CardTitle>
        </CardHeader>
        <CardContent>
          {status ? (
            <div className="flex items-center gap-4 text-sm">
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "h-2 w-2 rounded-full",
                    status.ollama_running ? "bg-success" : "bg-danger",
                  )}
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
        </CardContent>
      </Card>

      {/* Pull new model */}
      <Card>
        <CardHeader>
          <CardTitle className="text-text-muted">Pull Model</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handlePull} className="flex gap-3">
            <Input
              type="text"
              value={pullName}
              onChange={(e) => setPullName(e.target.value)}
              placeholder="e.g. qwen3:8b, phi4:14b"
              disabled={pulling}
              className="flex-1"
            />
            <Button type="submit" disabled={pulling || !pullName.trim()}>
              {pulling ? "Pulling..." : "Pull"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {error && <p className="text-sm text-destructive">{error}</p>}

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
              <Card
                key={model.name}
                className="transition-colors hover:border-accent"
              >
                <CardContent className="flex items-center justify-between p-3">
                  <div className="flex items-center gap-3">
                    <span
                      className={cn(
                        "h-2 w-2 rounded-full",
                        model.available ? "bg-success" : "bg-danger",
                      )}
                    />
                    <span className="font-mono text-sm">{model.name}</span>
                    {isDefault && (
                      <Badge variant="engine">DEFAULT</Badge>
                    )}
                    {isRunning && (
                      <Badge variant="info">RUNNING</Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {!isDefault && (
                      <Button
                        variant="ghost"
                        size="xs"
                        onClick={() => handleSwitch(model.name)}
                        disabled={loading}
                        className="font-mono text-accent"
                      >
                        Set Default
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="xs"
                      onClick={() => handleDelete(model.name)}
                      disabled={loading}
                      className={cn(
                        "font-mono",
                        confirm === model.name
                          ? "bg-destructive/20 text-destructive"
                          : "text-text-muted",
                      )}
                    >
                      {confirm === model.name ? "Confirm?" : "Delete"}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })
        )}
      </div>
    </div>
  );
}
