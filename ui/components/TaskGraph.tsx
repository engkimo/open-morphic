"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import {
  computeNodeDepths,
  computeGraphHeight,
  truncateWithEllipsis,
} from "@/lib/graphLayout";
import {
  Clock,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Zap,
  DollarSign,
  Wrench,
  RefreshCw,
  Database,
  X,
  Code2,
  Sparkles,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

/* ── Status → color mapping from theme ───────────────────────────── */

const STATUS_COLORS: Record<string, string> = {
  pending: "#2D2D42",
  running: "#38BDF8",
  success: "#10B981",
  failed: "#EF4444",
  fallback: "#F59E0B",
  degraded: "#F59E0B",
};

const X_GAP = 400;
const Y_GAP = 120;

/* ── Status icon for graph nodes ─────────────────────────────────── */

function NodeStatusIcon({ status }: { status: string }) {
  switch (status) {
    case "pending":
      return <Clock size={13} className="text-text-muted" />;
    case "running":
      return <Loader2 size={13} className="text-info animate-spin" />;
    case "success":
      return <CheckCircle2 size={13} className="text-success" />;
    case "failed":
      return <XCircle size={13} className="text-danger" />;
    default:
      return <AlertTriangle size={13} className="text-warning" />;
  }
}

/* ── Custom SubTask node ─────────────────────────────────────────── */

function SubTaskNode({ data }: NodeProps) {
  const d = data as {
    label: string;
    fullLabel: string;
    status: string;
    model_used: string | null;
    cost_usd: number;
    hasCode: boolean;
    complexity: string | null;
    engine_used: string | null;
    selected: boolean;
    isNew: boolean;
    enterDelay: number;
    prevStatus: string | null;
    onSelect: () => void;
    spawned_by_reflection: boolean;
    reflection_round: number | null;
  };
  const accentColor = STATUS_COLORS[d.status] || "#2D2D42";
  const isLocal = d.model_used?.startsWith("ollama/");
  const isRunning = d.status === "running";
  const statusChanged = d.prevStatus !== null && d.prevStatus !== d.status;

  const classNames = [
    "rounded-lg bg-surface px-3 py-2 shadow-md cursor-pointer",
    "transition-all duration-500",
    d.isNew ? "morphic-node-enter" : "",
    isRunning ? "morphic-node-pulse" : "",
    statusChanged ? "morphic-status-flash" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={classNames}
      style={{
        animationDelay: d.isNew ? `${d.enterDelay}ms` : undefined,
        borderTop: d.selected ? `2px solid ${accentColor}` : `1px solid #1E1E2E`,
        borderRight: d.selected ? `2px solid ${accentColor}` : `1px solid #1E1E2E`,
        borderBottom: d.selected ? `2px solid ${accentColor}` : `1px solid #1E1E2E`,
        borderLeft: `4px solid ${accentColor}`,
        minWidth: 240,
        maxWidth: 320,
        boxShadow: d.selected
          ? `0 0 12px ${accentColor}40`
          : isRunning
            ? `0 0 16px rgba(56,189,248,0.15)`
            : "0 1px 3px rgba(0,0,0,0.3)",
      }}
      title={d.fullLabel}
      onClick={d.onSelect}
    >
      <Handle type="target" position={Position.Left} />
      <div className="flex items-center gap-1.5">
        <NodeStatusIcon status={d.status} />
        <span className="text-sm font-medium text-text flex-1 min-w-0 truncate">
          {d.label}
        </span>
        {d.complexity && (
          <span className="rounded bg-accent/20 px-1.5 py-0.5 text-[9px] font-medium text-accent uppercase shrink-0">
            {d.complexity}
          </span>
        )}
        {isLocal && (
          <span className="rounded bg-emerald-900/50 px-1.5 py-0.5 text-[10px] font-bold text-emerald-400 shrink-0">
            FREE
          </span>
        )}
        {d.spawned_by_reflection && (
          <span className="rounded bg-warning/20 px-1.5 py-0.5 text-[9px] font-bold text-warning shrink-0">
            R{d.reflection_round || "?"}
          </span>
        )}
      </div>
      <div className="mt-1 flex items-center gap-2">
        {d.engine_used && (
          <span className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent">
            <Zap size={9} />
            {d.engine_used}
          </span>
        )}
        {d.model_used && d.status !== "pending" && (
          <span className="text-[10px] text-text-muted font-mono">
            {d.model_used.replace(/^ollama\//, "")}
          </span>
        )}
        <span className="ml-auto text-[10px] font-mono text-text-muted">
          ${d.cost_usd.toFixed(4)}
        </span>
      </div>
      {d.hasCode && (
        <div className="mt-1 text-[10px] text-emerald-400 font-mono flex items-center gap-1">
          <Code2 size={10} /> Code
        </div>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

const nodeTypes = { subtask: SubTaskNode };

/* ── Detail panel for selected subtask ───────────────────────────── */

function SubTaskPanel({
  subtask,
  onClose,
}: {
  subtask: SubTaskResponse;
  onClose: () => void;
}) {
  const accentColor = STATUS_COLORS[subtask.status] || "#2D2D42";
  return (
    <div className="absolute right-0 top-0 bottom-0 w-80 bg-surface border-l border-border overflow-y-auto z-10">
      <div className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <Badge
            className="text-xs font-bold uppercase"
            style={{
              color: accentColor,
              background: `${accentColor}20`,
              borderColor: "transparent",
            }}
          >
            {subtask.status}
          </Badge>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text"
          >
            <X size={18} />
          </button>
        </div>

        <h3 className="text-sm font-medium text-text">
          {subtask.description}
        </h3>

        <div className="grid grid-cols-2 gap-2 text-center">
          <Card className="bg-background">
            <CardContent className="p-2">
              <div className="text-sm font-bold font-mono text-local-free">
                ${subtask.cost_usd.toFixed(4)}
              </div>
              <div className="text-[10px] text-text-muted flex items-center justify-center gap-0.5">
                <DollarSign size={9} /> Cost
              </div>
            </CardContent>
          </Card>
          <Card className="bg-background">
            <CardContent className="p-2">
              <div className="text-sm font-bold font-mono text-accent truncate">
                {subtask.model_used?.replace(/^ollama\//, "") || "—"}
              </div>
              <div className="text-[10px] text-text-muted">Model</div>
            </CardContent>
          </Card>
        </div>

        {subtask.spawned_by_reflection && (
          <div className="text-xs text-warning flex items-center gap-1">
            <Sparkles size={11} />
            Spawned by reflection (round {subtask.reflection_round || "?"})
          </div>
        )}

        {subtask.engine_used && (
          <div className="text-xs text-text-muted flex items-center gap-1">
            <Zap size={11} className="text-accent" />
            Engine: <span className="text-accent">{subtask.engine_used}</span>
          </div>
        )}

        {(subtask.tool_calls_count ?? 0) > 0 && (
          <div className="text-xs text-text-muted flex items-center gap-1">
            <Wrench size={11} />
            Tool calls: {subtask.tool_calls_count}
            {(subtask.react_iterations ?? 0) > 0 && (
              <>
                {" "}| <RefreshCw size={9} /> ReAct: {subtask.react_iterations}
              </>
            )}
          </div>
        )}

        {(subtask.tools_used ?? []).length > 0 && (
          <div className="text-xs text-text-muted flex items-center gap-1">
            <Wrench size={11} />
            {subtask.tools_used!.join(", ")}
          </div>
        )}

        {(subtask.data_sources ?? []).length > 0 && (
          <div className="text-xs text-text-muted flex items-center gap-1">
            <Database size={11} />
            {subtask.data_sources!.join(", ")}
          </div>
        )}

        {subtask.dependencies.length > 0 && (
          <div className="text-xs text-text-muted">
            Dependencies: {subtask.dependencies.length} subtask(s)
          </div>
        )}

        {subtask.code && (
          <div>
            <div className="text-[10px] text-text-muted uppercase mb-1 flex items-center gap-1">
              <Code2 size={10} /> Code
            </div>
            <pre className="rounded bg-background border border-border p-2 text-[11px] text-text overflow-x-auto whitespace-pre-wrap font-mono max-h-40">
              {subtask.code}
            </pre>
          </div>
        )}

        {subtask.execution_output && (
          <div>
            <div className="text-[10px] text-text-muted uppercase mb-1">
              Output
            </div>
            <pre className="rounded bg-background border border-border p-2 text-[11px] text-text-muted overflow-x-auto whitespace-pre-wrap font-mono max-h-32">
              {subtask.execution_output}
            </pre>
          </div>
        )}

        {subtask.result && (
          <div>
            <div className="text-[10px] text-text-muted uppercase mb-1">
              Result
            </div>
            <pre className="rounded bg-background border border-border p-2 text-[11px] text-text overflow-x-auto whitespace-pre-wrap font-mono max-h-48">
              {subtask.result}
            </pre>
          </div>
        )}

        {subtask.error && (
          <div>
            <div className="text-[10px] text-danger uppercase mb-1 flex items-center gap-1">
              <XCircle size={10} /> Error
            </div>
            <pre className="rounded bg-danger/5 border border-danger/30 p-2 text-[11px] text-danger overflow-x-auto whitespace-pre-wrap font-mono max-h-32">
              {subtask.error}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Main graph component ────────────────────────────────────────── */

interface TaskGraphProps {
  task: TaskResponse;
}

export default function TaskGraph({ task }: TaskGraphProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selectedSubtask = task.subtasks.find(
    (st) => st.id === selectedId,
  );

  // Track previously seen node IDs for enter animation
  const prevNodeIds = useRef<Set<string>>(new Set());
  // Track previous status per node for status-change flash
  const prevStatusMap = useRef<Map<string, string>>(new Map());

  const handleNodeSelect = useCallback((id: string) => {
    setSelectedId((prev) => (prev === id ? null : id));
  }, []);

  const { nodes, edges, graphHeight } = useMemo(() => {
    const n: Node[] = [];
    const e: Edge[] = [];

    const depthMap = computeNodeDepths(task.subtasks);

    // Group subtasks by depth for Y positioning
    const depthGroups = new Map<number, string[]>();
    for (const st of task.subtasks) {
      const depth = depthMap.get(st.id) ?? 0;
      if (!depthGroups.has(depth)) depthGroups.set(depth, []);
      depthGroups.get(depth)!.push(st.id);
    }

    // Goal node
    const maxDepthNodes = Math.max(
      ...Array.from(depthGroups.values()).map((g) => g.length),
      1,
    );
    const goalY = ((maxDepthNodes - 1) * Y_GAP) / 2;

    const isGoalNew = !prevNodeIds.current.has("goal");
    n.push({
      id: "goal",
      type: "default",
      position: { x: 0, y: goalY },
      data: { label: truncateWithEllipsis(task.goal, 30) },
      className: isGoalNew ? "morphic-node-enter" : undefined,
      style: {
        background: "#12121A",
        color: "#E2E8F0",
        border: `2px solid ${STATUS_COLORS[task.status] || "#6366F1"}`,
        borderRadius: 8,
        padding: "8px 12px",
        fontWeight: 600,
        maxWidth: 250,
        transition: "border-color 0.5s ease",
      },
    });

    // Subtask nodes — with enter & status-change animation flags
    // Stagger delay: new nodes get incremental delay for cascade effect
    let newNodeIndex = 0;
    for (const st of task.subtasks) {
      const depth = depthMap.get(st.id) ?? 0;
      const group = depthGroups.get(depth) ?? [st.id];
      const indexInGroup = group.indexOf(st.id);
      const isNew = !prevNodeIds.current.has(st.id);
      const prevStatus = prevStatusMap.current.get(st.id) ?? null;
      const enterDelay = isNew ? newNodeIndex * 80 : 0;
      if (isNew) newNodeIndex++;

      n.push({
        id: st.id,
        type: "subtask",
        position: {
          x: (depth + 1) * X_GAP,
          y: indexInGroup * Y_GAP,
        },
        data: {
          label: truncateWithEllipsis(st.description, 35),
          fullLabel: st.description,
          status: st.status,
          model_used: st.model_used,
          cost_usd: st.cost_usd,
          hasCode: st.code != null,
          complexity: st.complexity,
          engine_used: st.engine_used ?? null,
          spawned_by_reflection: st.spawned_by_reflection ?? false,
          reflection_round: st.reflection_round ?? null,
          selected: st.id === selectedId,
          isNew,
          enterDelay,
          prevStatus,
          onSelect: () => handleNodeSelect(st.id),
        },
      });

      // Edge from goal to root subtasks
      if (st.dependencies.length === 0) {
        e.push({
          id: `goal-${st.id}`,
          source: "goal",
          target: st.id,
          type: "smoothstep",
          animated: st.status === "running",
          style: {
            stroke: STATUS_COLORS[st.status] || "#2D2D42",
            strokeWidth: st.status === "success" ? 2 : 1,
            transition: "stroke 0.5s ease, stroke-width 0.3s ease",
          },
        });
      }

      // Edges from dependencies
      for (const depId of st.dependencies) {
        e.push({
          id: `${depId}-${st.id}`,
          source: depId,
          target: st.id,
          type: "smoothstep",
          animated: st.status === "running",
          style: {
            stroke: STATUS_COLORS[st.status] || "#2D2D42",
            strokeWidth: st.status === "success" ? 2 : 1,
            transition: "stroke 0.5s ease, stroke-width 0.3s ease",
          },
        });
      }
    }

    return {
      nodes: n,
      edges: e,
      graphHeight: computeGraphHeight(task.subtasks.length),
    };
  }, [task, selectedId, handleNodeSelect]);

  // Update tracking refs after each render
  useEffect(() => {
    const ids = new Set(["goal", ...task.subtasks.map((st) => st.id)]);
    prevNodeIds.current = ids;
    const statusMap = new Map<string, string>();
    for (const st of task.subtasks) {
      statusMap.set(st.id, st.status);
    }
    prevStatusMap.current = statusMap;
  }, [task.subtasks]);

  return (
    <div className="relative">
      <div
        className="w-full rounded-lg border border-border bg-background"
        style={{ height: graphHeight }}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          proOptions={{ hideAttribution: true }}
          style={{ background: "#0A0A0F" }}
          onPaneClick={() => setSelectedId(null)}
        >
          <Background color="#1E1E2E" gap={20} />
          <Controls
            style={{ background: "#12121A", borderColor: "#1E1E2E" }}
          />
        </ReactFlow>
      </div>

      {/* Slide-out detail panel */}
      {selectedSubtask && (
        <SubTaskPanel
          subtask={selectedSubtask}
          onClose={() => setSelectedId(null)}
        />
      )}
    </div>
  );
}
