"use client";

import { useCallback, useMemo } from "react";
import {
  ReactFlow,
  Node,
  Edge,
  Position,
  Handle,
  Background,
  Controls,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { TaskResponse, SubTaskResponse } from "@/lib/api";

// Status → color mapping from theme
const STATUS_COLORS: Record<string, string> = {
  pending: "#2D2D42",
  running: "#38BDF8",
  success: "#10B981",
  failed: "#EF4444",
  fallback: "#F59E0B",
};

const STATUS_ICONS: Record<string, string> = {
  pending: "\u23F3",
  running: "\u26A1",
  success: "\u2713",
  failed: "\u2717",
  fallback: "\u21BB",
};

// Custom node component for subtasks
function SubTaskNode({ data }: NodeProps) {
  const d = data as {
    label: string;
    status: string;
    model_used: string | null;
    cost_usd: number;
    result: string | null;
  };
  const borderColor = STATUS_COLORS[d.status] || "#2D2D42";
  const icon = STATUS_ICONS[d.status] || "?";
  const isLocal = d.model_used?.startsWith("ollama/");

  return (
    <div
      className="rounded-lg border-2 bg-surface px-3 py-2 shadow-md"
      style={{ borderColor, minWidth: 180 }}
    >
      <Handle type="target" position={Position.Left} />
      <div className="flex items-center gap-1.5">
        <span
          className={`text-sm ${d.status === "running" ? "animate-pulse" : ""}`}
        >
          {icon}
        </span>
        <span className="text-sm font-medium text-text">{d.label}</span>
        {isLocal && (
          <span className="ml-auto rounded bg-emerald-900/50 px-1.5 py-0.5 text-[10px] font-bold text-emerald-400">
            FREE
          </span>
        )}
      </div>
      {d.model_used && (
        <div className="mt-1 text-[10px] text-text-muted">{d.model_used}</div>
      )}
      {d.result && (
        <div className="mt-1 truncate text-[10px] text-text-muted">
          {d.result.slice(0, 60)}
        </div>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

const nodeTypes = { subtask: SubTaskNode };

interface TaskGraphProps {
  task: TaskResponse;
}

export default function TaskGraph({ task }: TaskGraphProps) {
  const { nodes, edges } = useMemo(() => {
    const n: Node[] = [];
    const e: Edge[] = [];

    // Goal node
    n.push({
      id: "goal",
      type: "default",
      position: { x: 0, y: task.subtasks.length * 40 },
      data: { label: task.goal.slice(0, 40) },
      style: {
        background: "#12121A",
        color: "#E2E8F0",
        border: `2px solid ${STATUS_COLORS[task.status] || "#6366F1"}`,
        borderRadius: 8,
        padding: "8px 12px",
        fontWeight: 600,
      },
    });

    // Subtask nodes — topological layout
    task.subtasks.forEach((st, i) => {
      n.push({
        id: st.id,
        type: "subtask",
        position: { x: 250, y: i * 100 },
        data: {
          label: st.description.slice(0, 50),
          status: st.status,
          model_used: st.model_used,
          cost_usd: st.cost_usd,
          result: st.result,
        },
      });

      // Edge from goal to subtask (if no dependencies)
      if (st.dependencies.length === 0) {
        e.push({
          id: `goal-${st.id}`,
          source: "goal",
          target: st.id,
          animated: st.status === "running",
          style: { stroke: STATUS_COLORS[st.status] || "#2D2D42" },
        });
      }

      // Edges from dependencies
      st.dependencies.forEach((depId) => {
        e.push({
          id: `${depId}-${st.id}`,
          source: depId,
          target: st.id,
          animated: st.status === "running",
          style: { stroke: STATUS_COLORS[st.status] || "#2D2D42" },
        });
      });
    });

    return { nodes: n, edges: e };
  }, [task]);

  return (
    <div className="h-[400px] w-full rounded-lg border border-border bg-background">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        proOptions={{ hideAttribution: true }}
        style={{ background: "#0A0A0F" }}
      >
        <Background color="#1E1E2E" gap={20} />
        <Controls
          style={{ background: "#12121A", borderColor: "#1E1E2E" }}
        />
      </ReactFlow>
    </div>
  );
}
