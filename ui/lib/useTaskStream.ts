"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { TaskResponse } from "@/lib/api";
import { logger } from "@/lib/logger";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

/** A single SSE event received during task execution. */
export interface StreamEvent {
  type: string;
  timestamp?: number;
  subtask_id?: string;
  description?: string;
  status?: string;
  result?: string;
  model_used?: string;
  engine_used?: string;
  cost_usd?: number;
  error?: string;
  subtask_count?: number;
  total_cost_usd?: number;
  dependencies?: string[];
  subtasks?: { id: string; description: string; dependencies: string[] }[];
  // Living Fractal: reflection-driven dynamic node spawning (TD-163)
  spawned_by?: string;
  reflection_round?: number;
  satisfied?: boolean;
  spawned_count?: number;
  round?: number;
  parent_id?: string;
}

interface UseTaskStreamReturn {
  task: TaskResponse | null;
  events: StreamEvent[];
  isStreaming: boolean;
}

/**
 * React hook that connects to the SSE endpoint for real-time task updates.
 * Falls back to a single GET if the task is already complete.
 */
export function useTaskStream(taskId: string | null): UseTaskStreamReturn {
  const [task, setTask] = useState<TaskResponse | null>(null);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  const handleEvent = useCallback((eventType: string, data: StreamEvent) => {
    const event = { ...data, type: eventType };
    setEvents((prev) => [...prev, event]);

    if (eventType === "subtask_started") {
      setTask((prev) => {
        if (!prev) return prev;
        const subtasks = prev.subtasks.map((st) =>
          st.id === data.subtask_id ? { ...st, status: "running" } : st,
        );
        return { ...prev, subtasks };
      });
    }

    if (eventType === "subtask_completed") {
      setTask((prev) => {
        if (!prev) return prev;
        const subtasks = prev.subtasks.map((st) =>
          st.id === data.subtask_id
            ? {
                ...st,
                status: data.status || st.status,
                result: data.result || st.result,
                model_used: data.model_used || st.model_used,
                engine_used: data.engine_used || st.engine_used,
                cost_usd: data.cost_usd ?? st.cost_usd,
                error: data.error || st.error,
              }
            : st,
        );
        // Recompute progress and cost
        const done = subtasks.filter(
          (s) => s.status === "success" || s.status === "failed",
        ).length;
        const pct = subtasks.length > 0 ? Math.round((done / subtasks.length) * 100) : 0;
        const totalCost = subtasks.reduce((sum, s) => sum + (s.cost_usd ?? 0), 0);
        return { ...prev, subtasks, progress_pct: pct, total_cost_usd: totalCost };
      });
    }

    // Living Fractal: dynamically spawned node from reflection/expansion (TD-163, TD-174)
    if (eventType === "node_spawned") {
      setTask((prev) => {
        if (!prev) return prev;
        // Add new subtask if not already present
        const exists = prev.subtasks.some((st) => st.id === data.subtask_id);
        if (exists) return prev;
        const deps: string[] = data.parent_id ? [data.parent_id] : [];
        const newSubtask = {
          id: data.subtask_id || "",
          description: data.description || "",
          status: "pending" as const,
          dependencies: deps,
          result: null,
          error: null,
          code: null,
          execution_output: null,
          model_used: null,
          engine_used: null,
          cost_usd: 0,
          complexity: null,
          tool_calls_count: 0,
          react_iterations: 0,
          preferred_model: null,
          role: null,
          tools_used: [],
          data_sources: [],
          input_artifacts: {},
          output_artifacts: {},
          spawned_by_reflection: true,
          reflection_round: data.reflection_round ?? null,
        };
        const subtasks = [...prev.subtasks, newSubtask];
        return { ...prev, subtasks };
      });
    }

    if (eventType === "task_completed") {
      // Update task-level status and cost from the completed event
      setTask((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          status: data.status || prev.status,
          total_cost_usd: data.total_cost_usd ?? prev.total_cost_usd,
          is_complete: true,
          progress_pct: 100,
        };
      });
      setIsStreaming(false);
    }
  }, []);

  useEffect(() => {
    if (!taskId) return;

    const url = `${API_BASE}/api/tasks/${taskId}/stream`;
    logger.info(`SSE connecting — ${url}`);
    const es = new EventSource(url);
    esRef.current = es;
    setIsStreaming(true);

    es.addEventListener("snapshot", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      logger.debug("SSE snapshot received");
      setTask(data);

      // If snapshot shows task is complete, stop streaming
      if (data.is_complete) {
        setIsStreaming(false);
        es.close();
      }
    });

    es.addEventListener("task_started", (e: MessageEvent) => {
      handleEvent("task_started", JSON.parse(e.data));
    });

    es.addEventListener("subtask_started", (e: MessageEvent) => {
      handleEvent("subtask_started", JSON.parse(e.data));
    });

    es.addEventListener("subtask_completed", (e: MessageEvent) => {
      handleEvent("subtask_completed", JSON.parse(e.data));
    });

    es.addEventListener("task_completed", (e: MessageEvent) => {
      handleEvent("task_completed", JSON.parse(e.data));
    });

    // Living Fractal: reflection-driven dynamic node spawning (TD-163)
    es.addEventListener("node_spawned", (e: MessageEvent) => {
      handleEvent("node_spawned", JSON.parse(e.data));
    });

    es.addEventListener("reflection_started", (e: MessageEvent) => {
      handleEvent("reflection_started", JSON.parse(e.data));
    });

    es.addEventListener("reflection_complete", (e: MessageEvent) => {
      handleEvent("reflection_complete", JSON.parse(e.data));
    });

    es.addEventListener("error", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      logger.error("SSE error event", data);
      setIsStreaming(false);
      es.close();
    });

    es.onerror = () => {
      logger.warn("SSE connection error — closing");
      setIsStreaming(false);
      es.close();
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [taskId, handleEvent]);

  return { task, events, isStreaming };
}
