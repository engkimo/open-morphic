"use client";

import {
  Clock,
  Loader2,
  CheckCircle2,
  XCircle,
  Zap,
  Cpu,
  DollarSign,
  Play,
  Flag,
  Sparkles,
  Brain,
} from "lucide-react";
import type { StreamEvent } from "@/lib/useTaskStream";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

interface ActivityTimelineProps {
  events: StreamEvent[];
  isStreaming: boolean;
}

function EventIcon({
  type,
  status,
  stillRunning,
}: {
  type: string;
  status?: string;
  stillRunning?: boolean;
}) {
  if (type === "task_started") return <Play size={13} className="text-info" />;
  if (type === "task_completed")
    return <Flag size={13} className="text-success" />;
  if (type === "node_spawned")
    return <Sparkles size={13} className="text-accent" />;
  if (type === "reflection_started")
    return <Brain size={13} className="text-warning animate-pulse" />;
  if (type === "reflection_complete")
    return <Brain size={13} className="text-accent" />;
  if (type === "subtask_started") {
    if (stillRunning)
      return <Loader2 size={13} className="text-info animate-spin" />;
    return <CheckCircle2 size={13} className="text-success" />;
  }
  if (type === "subtask_completed") {
    if (status === "success")
      return <CheckCircle2 size={13} className="text-success" />;
    if (status === "failed")
      return <XCircle size={13} className="text-danger" />;
    return <Clock size={13} className="text-text-muted" />;
  }
  return <Clock size={13} className="text-text-muted" />;
}

function EventDescription({ event }: { event: StreamEvent }) {
  if (event.type === "task_started") {
    return (
      <span>
        Task started — {event.subtask_count} subtask(s)
      </span>
    );
  }

  if (event.type === "task_completed") {
    return (
      <span className="flex items-center gap-2">
        Task completed
        {event.total_cost_usd != null && (
          <span className="inline-flex items-center gap-0.5 text-text-muted">
            <DollarSign size={10} />
            {event.total_cost_usd.toFixed(4)}
          </span>
        )}
      </span>
    );
  }

  if (event.type === "subtask_started") {
    return (
      <span className="text-info">
        {event.description
          ? event.description.length > 80
            ? event.description.slice(0, 80) + "..."
            : event.description
          : "Subtask started"}
      </span>
    );
  }

  if (event.type === "subtask_completed") {
    return (
      <span className="flex items-center gap-2 flex-wrap">
        <span className={event.status === "failed" ? "text-danger" : ""}>
          {event.status === "failed" ? "Failed" : "Completed"}
        </span>
        {event.engine_used && (
          <Badge variant="engine" className="gap-0.5 text-[9px] px-1.5 py-0.5">
            <Zap size={8} />
            {event.engine_used}
          </Badge>
        )}
        {event.model_used && (
          <span className="inline-flex items-center gap-0.5 text-text-muted">
            <Cpu size={9} />
            {event.model_used.replace(/^ollama\//, "")}
          </span>
        )}
        {event.cost_usd != null && event.cost_usd > 0 && (
          <span className="inline-flex items-center gap-0.5 text-text-muted">
            <DollarSign size={9} />
            {event.cost_usd.toFixed(4)}
          </span>
        )}
        {event.cost_usd === 0 && (
          <Badge variant="free" className="text-[8px] px-1 py-0.5">
            FREE
          </Badge>
        )}
      </span>
    );
  }

  if (event.type === "node_spawned") {
    return (
      <span className="text-accent">
        Reflection spawned: {event.description || "new subtask"}
      </span>
    );
  }

  if (event.type === "reflection_started") {
    return (
      <span className="text-warning">
        Reflecting on completeness (round {event.round || "?"})...
      </span>
    );
  }

  if (event.type === "reflection_complete") {
    if (event.satisfied) {
      return <span className="text-success">Reflection: goal satisfied</span>;
    }
    return (
      <span className="text-accent">
        Reflection: spawning {event.spawned_count || 0} new node(s)
      </span>
    );
  }

  return <span>{event.type}</span>;
}

function ResultPreview({ result }: { result: string }) {
  if (!result) return null;
  const truncated = result.length > 200 ? result.slice(0, 200) + "..." : result;
  return (
    <div className="mt-1.5 rounded bg-background border border-border p-2 text-[11px] text-text-muted font-mono whitespace-pre-wrap max-h-24 overflow-hidden">
      {truncated}
    </div>
  );
}

export default function ActivityTimeline({
  events,
  isStreaming,
}: ActivityTimelineProps) {
  // Build set of subtask IDs that have completed (for spinner resolution)
  const completedSubtaskIds = new Set(
    events
      .filter((e) => e.type === "subtask_completed" && e.subtask_id)
      .map((e) => e.subtask_id),
  );

  return (
    <Card>
      <CardContent className="p-4">
        <div className="space-y-0">
          {events.map((event, i) => {
            // A subtask_started is "still running" only if streaming AND
            // no subsequent subtask_completed exists for this subtask
            const stillRunning =
              event.type === "subtask_started" &&
              isStreaming &&
              !completedSubtaskIds.has(event.subtask_id);

            return (
            <div
              key={i}
              className="flex gap-3 animate-in fade-in slide-in-from-left-2 duration-300"
              style={{ animationDelay: `${Math.min(i * 50, 500)}ms` }}
            >
              {/* Timeline line */}
              <div className="flex flex-col items-center">
                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-background border border-border">
                  <EventIcon
                    type={event.type}
                    status={event.status}
                    stillRunning={stillRunning}
                  />
                </div>
                {i < events.length - 1 && (
                  <div className="w-px flex-1 bg-border min-h-[16px]" />
                )}
                {i === events.length - 1 && isStreaming && (
                  <div className="w-px flex-1 bg-gradient-to-b from-border to-transparent min-h-[16px]" />
                )}
              </div>

              {/* Content */}
              <div className="flex-1 pb-3 min-w-0">
                <div className="text-xs font-mono leading-6">
                  <EventDescription event={event} />
                </div>
                {event.type === "subtask_completed" && event.result && (
                  <ResultPreview result={event.result} />
                )}
                {event.type === "subtask_completed" && event.error && (
                  <div className="mt-1.5 rounded bg-danger/5 border border-danger/30 p-2 text-[11px] text-danger font-mono whitespace-pre-wrap max-h-16 overflow-hidden">
                    {event.error}
                  </div>
                )}
              </div>

              {/* Timestamp */}
              <div className="text-[10px] text-text-muted font-mono leading-6 shrink-0">
                {event.timestamp
                  ? new Date(event.timestamp * 1000).toLocaleTimeString()
                  : ""}
              </div>
            </div>
            );
          })}

          {/* Streaming indicator */}
          {isStreaming && (
            <div className="flex gap-3 animate-pulse">
              <div className="flex flex-col items-center">
                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-info/10 border border-info/30">
                  <Loader2 size={12} className="text-info animate-spin" />
                </div>
              </div>
              <div className="flex-1 pb-3">
                <div className="text-xs font-mono text-info leading-6">
                  Processing...
                </div>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
