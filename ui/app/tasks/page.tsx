"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Clock,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
} from "lucide-react";
import {
  listTasks,
  deleteTask,
  type TaskResponse,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "pending":
      return <Clock size={18} className="text-text-muted" />;
    case "running":
      return <Loader2 size={18} className="text-info animate-spin" />;
    case "success":
      return <CheckCircle2 size={18} className="text-success" />;
    case "failed":
      return <XCircle size={18} className="text-danger" />;
    default:
      return <AlertTriangle size={18} className="text-warning" />;
  }
}

const STATUS_LABEL: Record<string, string> = {
  pending: "Pending",
  running: "Running",
  success: "Success",
  failed: "Failed",
  fallback: "Fallback",
};

export default function TasksPage() {
  const [tasks, setTasks] = useState<TaskResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("all");
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const refresh = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const data = await listTasks();
      setTasks(data.tasks);
    } catch {
      /* backend may be down */
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Auto-poll every 3s when any task is running or pending
  useEffect(() => {
    const hasActive = tasks.some(
      (t) => t.status === "running" || t.status === "pending",
    );
    if (!hasActive) return;
    const id = setInterval(() => refresh(true), 3000);
    return () => clearInterval(id);
  }, [tasks, refresh]);

  async function handleDelete(id: string) {
    if (confirmDelete !== id) {
      setConfirmDelete(id);
      return;
    }
    try {
      await deleteTask(id);
      setTasks((prev) => prev.filter((t) => t.id !== id));
      setConfirmDelete(null);
    } catch {
      /* ignore */
    }
  }

  const filtered =
    filter === "all"
      ? tasks
      : tasks.filter((t) => t.status === filter);

  const statusCounts = tasks.reduce<Record<string, number>>((acc, t) => {
    acc[t.status] = (acc[t.status] || 0) + 1;
    return acc;
  }, {});

  const totalCost = tasks.reduce((sum, t) => sum + (t.total_cost_usd ?? 0), 0);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/" className="text-sm text-text-muted hover:text-accent">
            &larr; Dashboard
          </Link>
          <h1 className="font-mono text-lg font-bold tracking-tight">
            Tasks
          </h1>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => refresh()}
          disabled={loading}
        >
          {loading ? "Loading..." : "Refresh"}
        </Button>
      </div>

      {/* Stats */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="text-center">
          <CardContent className="p-4">
            <div className="text-lg font-bold font-mono">{tasks.length}</div>
            <div className="text-xs text-text-muted mt-1">Total</div>
          </CardContent>
        </Card>
        <Card className="text-center">
          <CardContent className="p-4">
            <div className="text-lg font-bold font-mono text-success">
              {statusCounts.success || 0}
            </div>
            <div className="text-xs text-text-muted mt-1">Succeeded</div>
          </CardContent>
        </Card>
        <Card className="text-center">
          <CardContent className="p-4">
            <div className="text-lg font-bold font-mono text-danger">
              {statusCounts.failed || 0}
            </div>
            <div className="text-xs text-text-muted mt-1">Failed</div>
          </CardContent>
        </Card>
        <Card className="text-center">
          <CardContent className="p-4">
            <div className="text-lg font-bold font-mono">
              {totalCost === 0 ? (
                <span className="text-local-free">$0.00</span>
              ) : (
                `$${totalCost.toFixed(4)}`
              )}
            </div>
            <div className="text-xs text-text-muted mt-1">Total Cost</div>
          </CardContent>
        </Card>
      </div>

      {/* Filter Tabs */}
      <Tabs value={filter} onValueChange={setFilter}>
        <TabsList>
          {["all", "pending", "running", "success", "failed"].map((s) => (
            <TabsTrigger key={s} value={s}>
              {s === "all" ? "All" : (STATUS_LABEL[s] || s)}
              {s === "all" ? ` (${tasks.length})` : statusCounts[s] ? ` (${statusCounts[s]})` : ""}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {/* Task List */}
      {loading ? (
        <p className="py-8 text-center text-sm text-text-muted">Loading...</p>
      ) : filtered.length === 0 ? (
        <p className="py-8 text-center text-sm text-text-muted">
          {tasks.length === 0
            ? "No tasks yet. Create one from the Dashboard."
            : "No tasks match this filter."}
        </p>
      ) : (
        <div className="space-y-2">
          {filtered.map((task) => (
            <div
              key={task.id}
              className={`flex items-center justify-between rounded-lg border bg-surface px-4 py-3 transition-colors hover:border-accent ${
                task.status === "running"
                  ? "border-info/50 shadow-[0_0_8px_rgba(56,189,248,0.15)]"
                  : "border-border"
              }`}
            >
              <Link
                href={`/tasks/${task.id}`}
                className="flex items-center gap-3 flex-1 min-w-0"
              >
                <span className="shrink-0">
                  <StatusIcon status={task.status} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="font-mono text-sm truncate">{task.goal}</div>
                  <div className="flex items-center gap-3 mt-0.5 text-xs text-text-muted">
                    {(() => {
                      const subs = task.subtasks ?? [];
                      const done = subs.filter(
                        (s) => s.status === "success",
                      ).length;
                      return (
                        <span>
                          {done}/{subs.length} subtasks
                        </span>
                      );
                    })()}
                    {task.status === "running" && (() => {
                      const subs = task.subtasks ?? [];
                      const done = subs.filter(
                        (s) => s.status === "success",
                      ).length;
                      const pct = subs.length > 0 ? Math.round((done / subs.length) * 100) : 0;
                      return (
                        <span className="flex items-center gap-1.5">
                          <Progress
                            value={pct}
                            className="w-16"
                            indicatorClassName="bg-info"
                          />
                          <span className="text-info font-medium">{pct}%</span>
                        </span>
                      );
                    })()}
                    <span>
                      {new Date(task.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
              </Link>
              <div className="flex items-center gap-3 shrink-0 ml-4">
                {(() => {
                  const engines = [...new Set(
                    task.subtasks
                      .map((s) => s.engine_used)
                      .filter(Boolean) as string[],
                  )];
                  return engines.length > 0 ? (
                    <div className="flex gap-1">
                      {engines.map((eng) => (
                        <Badge key={eng} variant="engine" className="text-[9px] font-mono px-1.5 py-0.5">
                          {eng}
                        </Badge>
                      ))}
                    </div>
                  ) : null;
                })()}
                {(task.total_cost_usd ?? 0) === 0 ? (
                  <Badge variant="free" className="text-[10px]">FREE</Badge>
                ) : (
                  <span className="font-mono text-xs">
                    ${(task.total_cost_usd ?? 0).toFixed(4)}
                  </span>
                )}
                <Button
                  variant="ghost"
                  size="xs"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    handleDelete(task.id);
                  }}
                  className={
                    confirmDelete === task.id
                      ? "bg-danger/20 text-danger font-semibold"
                      : "text-text-muted hover:text-danger"
                  }
                >
                  {confirmDelete === task.id ? "Confirm?" : "Delete"}
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
