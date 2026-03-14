"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import GoalInput from "@/components/GoalInput";
import TaskList from "@/components/TaskList";
import CostMeter from "@/components/CostMeter";
import ModelStatus from "@/components/ModelStatus";
import {
  createTask,
  createPlan,
  listTasks,
  getCostSummary,
  getModelStatus,
  connectTaskWs,
  type TaskResponse,
  type ExecutionPlanResponse,
  type CostSummary,
  type ModelStatus as ModelStatusType,
} from "@/lib/api";

export default function Dashboard() {
  const router = useRouter();
  const [tasks, setTasks] = useState<TaskResponse[]>([]);
  const [cost, setCost] = useState<CostSummary | null>(null);
  const [models, setModels] = useState<ModelStatusType | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"execute" | "plan">("execute");

  const refresh = useCallback(async () => {
    try {
      const [taskList, costData, modelData] = await Promise.all([
        listTasks(),
        getCostSummary(),
        getModelStatus(),
      ]);
      setTasks(taskList.tasks);
      setCost(costData);
      setModels(modelData);
    } catch {
      /* backend may be down */
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handleSubmit(goal: string) {
    setLoading(true);
    setError(null);
    try {
      if (mode === "plan") {
        const plan = await createPlan(goal);
        router.push(`/plans/${plan.id}`);
      } else {
        const result = await createTask(goal) as TaskResponse | ExecutionPlanResponse;

        // Plan-first flow: API may return a plan instead of a task
        if ("steps" in result) {
          router.push(`/plans/${result.id}`);
          return;
        }

        const task = result as TaskResponse;
        setTasks((prev) => [task, ...prev]);

        // Subscribe to real-time updates
        connectTaskWs(
          task.id,
          (updated) => {
            setTasks((prev) =>
              prev.map((t) => (t.id === updated.id ? updated : t)),
            );
          },
          () => {
            refresh(); // refresh cost etc. when done
          },
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_280px]">
      <div className="space-y-6">
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border border-border">
            <button
              onClick={() => setMode("execute")}
              className={`px-3 py-1.5 text-sm font-medium ${
                mode === "execute"
                  ? "bg-accent text-white"
                  : "text-text-muted hover:text-text"
              } rounded-l-lg`}
            >
              Execute
            </button>
            <button
              onClick={() => setMode("plan")}
              className={`px-3 py-1.5 text-sm font-medium ${
                mode === "plan"
                  ? "bg-accent text-white"
                  : "text-text-muted hover:text-text"
              } rounded-r-lg`}
            >
              Plan First
            </button>
          </div>
        </div>
        <GoalInput onSubmit={handleSubmit} disabled={loading} />
        {error && (
          <p className="text-sm text-danger">{error}</p>
        )}
        <TaskList tasks={tasks} />
      </div>
      <div className="space-y-4">
        <ModelStatus status={models} />
        <CostMeter cost={cost} />
      </div>
    </div>
  );
}
