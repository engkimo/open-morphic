"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import TaskDetail from "@/components/TaskDetail";
import { getTask, connectTaskWs, type TaskResponse } from "@/lib/api";

export default function TaskPage() {
  const params = useParams<{ id: string }>();
  const [task, setTask] = useState<TaskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!params.id) return;

    getTask(params.id)
      .then((data) => {
        setTask(data);
        if (!data.is_complete) {
          connectTaskWs(params.id, (updated) => setTask(updated));
        }
      })
      .catch(() => setError("Task not found"));
  }, [params.id]);

  return (
    <div className="space-y-4">
      <Link
        href="/"
        className="inline-block text-sm text-text-muted hover:text-accent"
      >
        &larr; Back to Dashboard
      </Link>

      {error && <p className="text-danger">{error}</p>}
      {task && <TaskDetail task={task} />}
    </div>
  );
}
