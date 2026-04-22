"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import TaskDetail from "@/components/TaskDetail";
import TaskGraph from "@/components/TaskGraph";
import ActivityTimeline from "@/components/ActivityTimeline";
import { useTaskStream } from "@/lib/useTaskStream";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export default function TaskPage() {
  const params = useParams<{ id: string }>();
  const { task, events, isStreaming } = useTaskStream(params.id ?? null);
  const [showTimeline, setShowTimeline] = useState(true);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Button variant="link" size="sm" asChild>
          <Link href="/">
            &larr; Back to Dashboard
          </Link>
        </Button>
        {isStreaming && (
          <Badge variant="info" className="gap-2 font-mono">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-info opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-info" />
            </span>
            Live
          </Badge>
        )}
      </div>

      {!task && (
        <div className="py-12 text-center">
          <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
          <p className="mt-2 text-sm text-text-muted">Loading task...</p>
        </div>
      )}

      {task && (
        <>
          <TaskDetail task={task} />

          {/* Activity Timeline — deep research style */}
          {events.length > 0 && (
            <div>
              <Button
                variant="ghost"
                size="xs"
                onClick={() => setShowTimeline(!showTimeline)}
                className="mb-2 font-mono text-text-muted hover:text-accent"
              >
                {showTimeline ? "Hide" : "Show"} Activity ({events.length} events)
              </Button>
              {showTimeline && (
                <ActivityTimeline events={events} isStreaming={isStreaming} />
              )}
            </div>
          )}

          {task.subtasks.length > 0 && <TaskGraph task={task} />}
        </>
      )}
    </div>
  );
}
