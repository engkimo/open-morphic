"use client";

import { useCallback, useEffect, useState } from "react";
import GoalInput from "@/components/GoalInput";
import TaskList from "@/components/TaskList";
import CostMeter from "@/components/CostMeter";
import ModelStatus from "@/components/ModelStatus";
import {
  createTask,
  listTasks,
  getCostSummary,
  getModelStatus,
  connectTaskWs,
  type TaskResponse,
  type CostSummary,
  type ModelStatus as ModelStatusType,
} from "@/lib/api";

export default function Dashboard() {
  const [tasks, setTasks] = useState<TaskResponse[]>([]);
  const [cost, setCost] = useState<CostSummary | null>(null);
  const [models, setModels] = useState<ModelStatusType | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      const task = await createTask(goal);
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
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create task");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_280px]">
      <div className="space-y-6">
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
