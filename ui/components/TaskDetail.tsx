"use client";

import { useEffect, useRef, useState } from "react";
import type { TaskResponse } from "@/lib/api";
import { parseResultWithComplexity } from "@/lib/resultParser";
import CodeBlock from "./CodeBlock";
import ExecutionResult from "./ExecutionResult";
import {
  Clock,
  Loader2,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronRight,
  DollarSign,
  GitBranch,
  Cpu,
  Wrench,
  Database,
  Zap,
  RefreshCw,
  AlertTriangle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from "@/components/ui/collapsible";

/* ── Status icon mapping ─────────────────────────────────────────── */

function StatusIcon({
  status,
  className = "",
}: {
  status: string;
  className?: string;
}) {
  const base = "shrink-0 " + className;
  switch (status) {
    case "pending":
      return <Clock className={`${base} text-text-muted`} size={16} />;
    case "running":
      return (
        <Loader2 className={`${base} text-info animate-spin`} size={16} />
      );
    case "success":
      return (
        <CheckCircle2 className={`${base} text-success`} size={16} />
      );
    case "failed":
      return <XCircle className={`${base} text-danger`} size={16} />;
    case "degraded":
      return (
        <AlertTriangle className={`${base} text-warning`} size={16} />
      );
    default:
      return <Clock className={`${base} text-text-muted`} size={16} />;
  }
}

/* ── Animated counter for stats ──────────────────────────────────── */

function AnimatedNumber({
  value,
  prefix = "",
  suffix = "",
  decimals = 0,
  className = "",
}: {
  value: number;
  prefix?: string;
  suffix?: string;
  decimals?: number;
  className?: string;
}) {
  const [display, setDisplay] = useState(value);
  const prev = useRef(value);

  useEffect(() => {
    if (prev.current === value) return;
    const from = prev.current;
    const diff = value - from;
    const steps = 20;
    let step = 0;
    const timer = setInterval(() => {
      step++;
      setDisplay(from + diff * (step / steps));
      if (step >= steps) {
        clearInterval(timer);
        setDisplay(value);
      }
    }, 25);
    prev.current = value;
    return () => clearInterval(timer);
  }, [value]);

  return (
    <span className={className}>
      {prefix}
      {display.toFixed(decimals)}
      {suffix}
    </span>
  );
}

/* ── Running skeleton ────────────────────────────────────────────── */

function RunningPulse() {
  return (
    <div className="mt-3 space-y-2 animate-pulse">
      <div className="h-3 w-3/4 rounded bg-info/10" />
      <div className="h-3 w-1/2 rounded bg-info/10" />
      <div className="h-3 w-2/3 rounded bg-info/10" />
    </div>
  );
}

/* ── Main component ──────────────────────────────────────────────── */

interface TaskDetailProps {
  task: TaskResponse;
}

export default function TaskDetail({ task }: TaskDetailProps) {
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="font-mono text-lg font-semibold">{task.goal}</h2>
        <Badge
          variant={
            task.status === "running"
              ? "info"
              : task.status === "success"
                ? "success"
                : task.status === "failed"
                  ? "destructive"
                  : "outline"
          }
          className="gap-1.5"
        >
          <StatusIcon status={task.status} />
          {task.status}
        </Badge>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-4 text-center text-sm">
        <Card>
          <CardContent className="p-3">
            <AnimatedNumber
              value={Math.round(task.success_rate * 100)}
              suffix="%"
              className="text-lg font-bold text-accent"
            />
            <div className="text-text-muted flex items-center justify-center gap-1 mt-0.5">
              <CheckCircle2 size={12} /> Success
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-3">
            <div className="text-lg font-bold flex items-center justify-center gap-1">
              <GitBranch size={18} className="text-text-muted" />
              {task.subtasks.length}
            </div>
            <div className="text-text-muted">Subtasks</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-3">
            <AnimatedNumber
              value={task.total_cost_usd}
              prefix="$"
              decimals={4}
              className="text-lg font-bold text-local-free"
            />
            <div className="text-text-muted flex items-center justify-center gap-1 mt-0.5">
              <DollarSign size={12} /> Cost
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Subtask list */}
      <div className="space-y-2">
        <h3 className="font-mono text-sm font-semibold text-text-muted flex items-center gap-1.5">
          <Cpu size={14} /> Subtasks
        </h3>
        {task.subtasks.map((st) => {
          const { answer, reasoning, parsed } = parseResultWithComplexity(
            st.result,
            st.complexity,
          );
          const hasCode = st.code != null;
          const isSimple = st.complexity === "simple";
          const isRunning = st.status === "running";
          const isPending = st.status === "pending";
          const isExpanded = expanded === st.id;

          return (
            <Card
              key={st.id}
              className={`px-4 py-3 transition-all duration-300 ${
                isRunning
                  ? "border-info/40 shadow-[0_0_12px_rgba(56,189,248,0.08)]"
                  : st.status === "success"
                    ? "border-success/20"
                    : st.status === "failed"
                      ? "border-danger/30"
                      : ""
              }`}
            >
              {/* Subtask header — clickable */}
              <div
                className="flex items-start gap-3 cursor-pointer"
                onClick={() =>
                  setExpanded(isExpanded ? null : st.id)
                }
              >
                <StatusIcon
                  status={st.status}
                  className="mt-0.5"
                />
                <div className="flex-1 min-w-0">
                  <div className="font-mono text-sm">{st.description}</div>

                  {/* Badges row */}
                  <div className="flex gap-2 mt-1.5 flex-wrap items-center">
                    {st.engine_used && (
                      <Badge variant="engine" className="gap-1 text-[10px] px-1.5 py-0.5">
                        <Zap size={10} />
                        {st.engine_used}
                      </Badge>
                    )}
                    {st.model_used && st.status !== "pending" && (
                      <Badge variant="outline" className="text-[10px] px-1.5 py-0.5 font-mono">
                        {st.model_used.replace(/^ollama\//, "")}
                      </Badge>
                    )}
                    {st.model_used?.startsWith("ollama/") && st.status !== "pending" && (
                      <Badge variant="free" className="text-[9px] px-1 py-0.5">
                        FREE
                      </Badge>
                    )}
                    {st.spawned_by_reflection && (
                      <Badge variant="warning" className="text-[9px] px-1 py-0.5 font-bold">
                        REFLECT R{st.reflection_round || "?"}
                      </Badge>
                    )}
                    {(st.react_iterations ?? 0) > 0 && (
                      <Badge variant="info" className="gap-0.5 text-[10px] px-1.5 py-0.5">
                        <RefreshCw size={9} />
                        ReAct:{st.react_iterations}
                      </Badge>
                    )}
                    {(st.tool_calls_count ?? 0) > 0 && (
                      <Badge variant="info" className="gap-0.5 text-[10px] px-1.5 py-0.5">
                        <Wrench size={9} />
                        {st.tool_calls_count}
                      </Badge>
                    )}
                    {st.cost_usd > 0 && (
                      <span className="text-[10px] font-mono text-text-muted ml-auto">
                        ${st.cost_usd.toFixed(4)}
                      </span>
                    )}
                  </div>
                </div>

                {/* Expand chevron */}
                {!isPending && (
                  <span className="text-text-muted mt-0.5">
                    {isExpanded ? (
                      <ChevronDown size={16} />
                    ) : (
                      <ChevronRight size={16} />
                    )}
                  </span>
                )}
              </div>

              {/* Running skeleton */}
              {isRunning && !st.result && <RunningPulse />}

              {/* Code execution result */}
              {hasCode && (
                <div className="mt-3">
                  <ExecutionResult
                    code={st.code!}
                    output={st.execution_output}
                    success={st.status === "success"}
                  />
                </div>
              )}

              {/* SIMPLE task: large prominent answer */}
              {!hasCode && st.result && isSimple && (
                <div className="mt-3 rounded-lg border border-accent/20 bg-accent/5 px-4 py-3 text-center animate-in fade-in duration-500">
                  <div className="text-2xl font-bold text-accent">
                    {answer}
                  </div>
                </div>
              )}

              {/* MEDIUM/COMPLEX task: structured result */}
              {!hasCode && st.result && !isSimple && (
                <div className="mt-2 animate-in fade-in slide-in-from-bottom-2 duration-500">
                  {parsed.type === "json" || parsed.type === "code" ? (
                    <CodeBlock
                      code={parsed.content}
                      language={parsed.language}
                    />
                  ) : (
                    <div className="text-xs text-text-muted whitespace-pre-wrap">
                      {parsed.content}
                    </div>
                  )}

                  {/* Collapsible reasoning */}
                  {reasoning && (
                    <Collapsible>
                      <CollapsibleTrigger className="mt-2 cursor-pointer text-xs text-text-muted hover:text-text">
                        Show reasoning process
                      </CollapsibleTrigger>
                      <CollapsibleContent>
                        <div className="mt-1 rounded border border-border bg-background px-3 py-2 text-xs text-text-muted whitespace-pre-wrap">
                          {reasoning}
                        </div>
                      </CollapsibleContent>
                    </Collapsible>
                  )}
                </div>
              )}

              {/* Error display */}
              {st.error && (
                <Card className="mt-2 border-danger/30 bg-danger/10">
                  <CardContent className="px-3 py-2 flex items-start gap-2 text-xs text-danger">
                    <XCircle size={14} className="shrink-0 mt-0.5" />
                    {st.error}
                  </CardContent>
                </Card>
              )}

              {/* Expanded subtask detail */}
              {isExpanded && (
                <div className="mt-2 p-3 bg-background rounded border border-border text-sm space-y-2 animate-in fade-in slide-in-from-top-1 duration-200">
                  {st.result && (
                    <div>
                      <span className="text-text-muted text-xs">Result:</span>
                      <pre className="mt-1 whitespace-pre-wrap text-text text-xs">
                        {st.result}
                      </pre>
                    </div>
                  )}
                  {(st.tools_used ?? []).length > 0 && (
                    <div className="text-xs text-text-muted flex items-center gap-1">
                      <Wrench size={11} />
                      Tools: {st.tools_used!.join(", ")}
                    </div>
                  )}
                  {(st.data_sources ?? []).length > 0 && (
                    <div className="text-xs text-text-muted flex items-center gap-1">
                      <Database size={11} />
                      Sources: {st.data_sources!.join(", ")}
                    </div>
                  )}
                  {st.preferred_model &&
                    st.preferred_model !== st.model_used && (
                      <div className="text-xs text-warning flex items-center gap-1">
                        <AlertTriangle size={11} />
                        Requested: {st.preferred_model} / Actual:{" "}
                        {st.model_used}
                      </div>
                    )}
                  <div className="text-xs text-text-muted flex items-center gap-1">
                    <DollarSign size={11} />
                    Cost: ${st.cost_usd.toFixed(6)}
                  </div>
                </div>
              )}
            </Card>
          );
        })}
      </div>

      {/* Final Output */}
      {task.status === "success" && (
        <Card className="border-success/30 bg-success/5 animate-in fade-in slide-in-from-bottom-3 duration-700">
          <CardContent className="p-5">
            <h3 className="font-mono text-sm font-bold text-success mb-3 flex items-center gap-2">
              <CheckCircle2 size={16} className="text-success" />
              Final Answer
            </h3>
            <div className="whitespace-pre-wrap text-sm text-text leading-relaxed">
              {(task as TaskResponse & { final_answer?: string }).final_answer ??
                task.subtasks
                  .filter((st) => st.status === "success" && st.result)
                  .map((st) => st.result)
                  .join("\n\n---\n\n")}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Error summary for failed tasks */}
      {task.status === "failed" && (
        <Card className="border-danger/30 bg-danger/5">
          <CardContent className="p-4">
            <h3 className="font-mono text-sm font-semibold text-danger mb-2 flex items-center gap-1.5">
              <XCircle size={14} />
              Errors
            </h3>
            <div className="whitespace-pre-wrap text-sm text-text">
              {task.subtasks
                .filter((st) => st.error)
                .map((st) => `${st.description}: ${st.error}`)
                .join("\n\n")}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
