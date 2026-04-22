"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Clock,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Circle,
} from "lucide-react";
import GoalInput from "@/components/GoalInput";
import TaskList from "@/components/TaskList";
import CostMeter from "@/components/CostMeter";
import ModelStatus from "@/components/ModelStatus";
import { useAutoRefresh } from "@/lib/useAutoRefresh";
import {
  createTask,
  createPlan,
  listTasks,
  listEngines,
  getCostSummary,
  getModelStatus,
  type TaskResponse,
  type ExecutionPlanResponse,
  type CostSummary,
  type ModelStatus as ModelStatusType,
  type EngineInfoResponse,
  type CreateTaskOptions,
} from "@/lib/api";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

function QuickStats({
  tasks,
  engines,
  cost,
}: {
  tasks: TaskResponse[];
  engines: EngineInfoResponse[];
  cost: CostSummary | null;
}) {
  const total = tasks.length;
  const success = tasks.filter((t) => t.status === "success").length;
  const running = tasks.filter((t) => t.status === "running").length;
  const rate = total > 0 ? Math.round((success / total) * 100) : 0;
  const online = engines.filter((e) => e.available).length;
  const localPct = cost ? Math.round(cost.local_usage_rate * 100) : 0;

  const stats = [
    { label: "Tasks", value: total.toString(), color: "text-foreground" },
    { label: "Success Rate", value: `${rate}%`, color: rate >= 70 ? "text-success" : rate >= 40 ? "text-warning" : "text-danger" },
    { label: "Running", value: running.toString(), color: running > 0 ? "text-info" : "text-text-muted" },
    { label: "Engines", value: `${online}/${engines.length}`, color: online > 0 ? "text-success" : "text-danger" },
    { label: "Local", value: `${localPct}%`, color: "text-local-free" },
  ];

  return (
    <div className="grid grid-cols-5 gap-3">
      {stats.map((s) => (
        <Card key={s.label}>
          <CardContent className="p-3 text-center">
            <div className={cn("text-lg font-bold font-mono", s.color)}>
              {s.value}
            </div>
            <div className="text-[10px] text-text-muted">{s.label}</div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function EngineWidget({ engines }: { engines: EngineInfoResponse[] }) {
  if (engines.length === 0) return null;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="text-text-muted">Engines</CardTitle>
        <Link href="/engines" className="text-[10px] text-accent hover:underline">
          View all
        </Link>
      </CardHeader>
      <CardContent className="space-y-1.5">
        {engines.map((e) => (
          <div key={e.engine_type} className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-1.5">
              <Circle
                size={8}
                className={e.available ? "text-success fill-success" : "text-danger fill-danger"}
              />
              <span className="font-mono">{e.engine_type}</span>
            </div>
            {e.cost_per_hour_usd === 0 && e.available && (
              <Badge variant="free" className="px-1 py-0 text-[8px]">FREE</Badge>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function ActivityFeed({ tasks }: { tasks: TaskResponse[] }) {
  const recent = tasks.slice(0, 8);

  if (recent.length === 0) return null;

  function StatusIcon({ status }: { status: string }) {
    switch (status) {
      case "pending":
        return <Clock size={14} className="text-text-muted shrink-0" />;
      case "running":
        return <Loader2 size={14} className="text-info animate-spin shrink-0" />;
      case "success":
        return <CheckCircle2 size={14} className="text-success shrink-0" />;
      case "failed":
        return <XCircle size={14} className="text-danger shrink-0" />;
      default:
        return <AlertTriangle size={14} className="text-warning shrink-0" />;
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="text-text-muted">Recent Activity</CardTitle>
        <Link href="/tasks" className="text-[10px] text-accent hover:underline">
          View all
        </Link>
      </CardHeader>
      <CardContent className="space-y-2">
        {recent.map((t) => (
          <Link
            key={t.id}
            href={`/tasks/${t.id}`}
            className="flex items-center justify-between rounded border border-border/50 bg-background px-3 py-2 text-xs transition-colors hover:border-accent"
          >
            <div className="flex items-center gap-2 min-w-0">
              <StatusIcon status={t.status} />
              <span className="truncate font-mono">{t.goal}</span>
            </div>
            <div className="flex items-center gap-3 flex-shrink-0 ml-2">
              <Badge variant="outline" className="font-normal">
                {t.subtasks.length} subtask{t.subtasks.length !== 1 ? "s" : ""}
              </Badge>
              {t.total_cost_usd === 0 ? (
                <span className="text-local-free font-mono">$0</span>
              ) : (
                <span className="font-mono">${t.total_cost_usd.toFixed(4)}</span>
              )}
            </div>
          </Link>
        ))}
      </CardContent>
    </Card>
  );
}

export default function Dashboard() {
  const router = useRouter();
  const [tasks, setTasks] = useState<TaskResponse[]>([]);
  const [engines, setEngines] = useState<EngineInfoResponse[]>([]);
  const [cost, setCost] = useState<CostSummary | null>(null);
  const [models, setModels] = useState<ModelStatusType | null>(null);
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"execute" | "plan">("execute");

  const refresh = useCallback(async () => {
    try {
      const [taskList, engineList, costData, modelData] = await Promise.all([
        listTasks(),
        listEngines(),
        getCostSummary(),
        getModelStatus(),
      ]);
      setTasks(taskList.tasks);
      setEngines(engineList.engines);
      setCost(costData);
      setModels(modelData);
    } catch {
      /* backend may be down */
    } finally {
      setInitialLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // TD-170: Auto-refresh when tasks are running/pending
  const hasActive = tasks.some(
    (t) => t.status === "running" || t.status === "pending",
  );
  useAutoRefresh(refresh, hasActive);

  async function handleSubmit(goal: string, options?: CreateTaskOptions) {
    setLoading(true);
    setError(null);
    try {
      if (mode === "plan") {
        const plan = await createPlan(goal);
        router.push(`/plans/${plan.id}`);
      } else {
        const result = await createTask(goal, options) as TaskResponse | ExecutionPlanResponse;

        // Plan-first flow: API may return a plan instead of a task
        if ("steps" in result) {
          router.push(`/plans/${result.id}`);
          return;
        }

        const task = result as TaskResponse;
        // Navigate to task detail for live SSE stream (TD-163 fractal)
        router.push(`/tasks/${task.id}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Quick Stats */}
      {initialLoading ? (
        <div className="grid grid-cols-5 gap-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-3 text-center">
                <Skeleton className="h-6 w-10 mx-auto mb-1" />
                <Skeleton className="h-3 w-12 mx-auto" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <QuickStats tasks={tasks} engines={engines} cost={cost} />
      )}

      {/* Main content area */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_280px]">
        <div className="space-y-6">
          {/* Mode toggle + Goal input */}
          <Tabs value={mode} onValueChange={(v) => setMode(v as "execute" | "plan")}>
            <TabsList>
              <TabsTrigger value="execute">Execute</TabsTrigger>
              <TabsTrigger value="plan">Plan First</TabsTrigger>
            </TabsList>
          </Tabs>
          <GoalInput onSubmit={handleSubmit} disabled={loading} engines={engines} />
          {error && (
            <Badge variant="destructive" className="text-sm">{error}</Badge>
          )}

          {/* Recent Activity */}
          <ActivityFeed tasks={tasks} />

          {/* Full Task List */}
          <TaskList tasks={tasks} loading={initialLoading} />
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          <EngineWidget engines={engines} />
          <ModelStatus status={models} />
          <CostMeter cost={cost} />
        </div>
      </div>
    </div>
  );
}
