"use client";

import type { ToolCandidateResponse } from "@/lib/api";
import SafetyBadge from "./SafetyBadge";
import InstallButton from "./InstallButton";

interface ToolCardProps {
  tool: ToolCandidateResponse;
  installed?: boolean;
  onInstall: (name: string) => Promise<void>;
  onUninstall?: (name: string) => Promise<void>;
}

export default function ToolCard({
  tool,
  installed,
  onInstall,
  onUninstall,
}: ToolCardProps) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border border-border bg-surface px-4 py-3 transition-colors hover:border-accent">
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-semibold text-foreground">
            {tool.name}
          </span>
          <SafetyBadge tier={tool.safety_tier} score={tool.safety_score} />
        </div>
        {tool.description && (
          <p className="text-xs text-text-muted line-clamp-2">
            {tool.description}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-3 text-xs text-text-muted">
          {tool.publisher && <span>by {tool.publisher}</span>}
          {tool.transport && (
            <span className="rounded bg-border px-1.5 py-0.5">
              {tool.transport}
            </span>
          )}
          {tool.download_count > 0 && (
            <span>{tool.download_count.toLocaleString()} downloads</span>
          )}
        </div>
      </div>
      <div className="shrink-0 pt-1">
        <InstallButton
          toolName={tool.name}
          installed={installed}
          onInstall={onInstall}
          onUninstall={onUninstall}
        />
      </div>
    </div>
  );
}
