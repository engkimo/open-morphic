"use client";

import Link from "next/link";
import type { TaskResponse } from "@/lib/api";
import {
  Clock,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  GitBranch,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Card } from "@/components/ui/card";

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "pending":
      return <Clock className="text-text-muted" size={18} />;
    case "running":
      return <Loader2 className="text-info animate-spin" size={18} />;
    case "success":
      return <CheckCircle2 className="text-success" size={18} />;
    case "failed":
      return <XCircle className="text-danger" size={18} />;
    default:
      return <AlertTriangle className="text-warning" size={18} />;
  }
}

function SkeletonRow() {
  return (
    <Card className="flex items-center justify-between px-4 py-3">
      <div className="flex items-center gap-3">
        <Skeleton className="h-[18px] w-[18px] rounded-full" />
        <Skeleton className="h-4 w-48" />
      </div>
      <div className="flex items-center gap-4">
        <Skeleton className="h-3 w-8" />
        <Skeleton className="h-5 w-12" />
      </div>
    </Card>
  );
}

interface TaskListProps {
  tasks: TaskResponse[];
  loading?: boolean;
}

export default function TaskList({ tasks, loading }: TaskListProps) {
  if (loading) {
    return (
      <div className="space-y-2">
        <SkeletonRow />
        <SkeletonRow />
        <SkeletonRow />
      </div>
    );
  }

  if (tasks.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-text-muted">
        No tasks yet. Enter a goal above to get started.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {tasks.map((task) => (
        <Link
          key={task.id}
          href={`/tasks/${task.id}`}
          className="block"
        >
          <Card className="flex items-center justify-between px-4 py-3 transition-colors hover:border-accent">
            <div className="flex items-center gap-3">
              <StatusIcon status={task.status} />
              <span className="font-mono text-sm">{task.goal}</span>
            </div>
            <div className="flex items-center gap-4 text-xs text-text-muted">
              <Badge variant="outline" className="gap-1 font-normal">
                <GitBranch size={12} />
                {(task.subtasks ?? []).length}
              </Badge>
              {(task.total_cost_usd ?? 0) === 0 ? (
                <Badge variant="free">FREE</Badge>
              ) : (
                <span>${(task.total_cost_usd ?? 0).toFixed(4)}</span>
              )}
            </div>
          </Card>
        </Link>
      ))}
    </div>
  );
}
