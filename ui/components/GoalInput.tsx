"use client";

import { useState } from "react";
import { CheckCircle2, XCircle, ChevronDown, ChevronUp } from "lucide-react";
import type { CreateTaskOptions } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

const ENGINE_OPTIONS = [
  { value: "", label: "Auto-route", desc: "Best engine for the task" },
  { value: "ollama", label: "Ollama", desc: "Local LLM (FREE)" },
  { value: "claude_code", label: "Claude Code", desc: "Complex reasoning" },
  { value: "gemini_cli", label: "Gemini CLI", desc: "Long context (2M)" },
  { value: "codex_cli", label: "Codex CLI", desc: "Fast code gen" },
  { value: "openhands", label: "OpenHands", desc: "Docker sandbox" },
  { value: "adk", label: "ADK", desc: "Workflow pipeline" },
];

interface GoalInputProps {
  onSubmit: (goal: string, options?: CreateTaskOptions) => void;
  disabled?: boolean;
  engines?: { engine_type: string; available: boolean }[];
}

export default function GoalInput({ onSubmit, disabled, engines }: GoalInputProps) {
  const [goal, setGoal] = useState("");
  const [engine, setEngine] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [fractalDepth, setFractalDepth] = useState<number | null>(null);
  const [fractalConcurrency, setFractalConcurrency] = useState<number | null>(null);
  const [fractalDelay, setFractalDelay] = useState<number | null>(null);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = goal.trim();
    if (!trimmed) return;
    onSubmit(trimmed, {
      engine: engine || null,
      fractal_max_depth: fractalDepth,
      fractal_max_concurrent_nodes: fractalConcurrency,
      fractal_throttle_delay_ms: fractalDelay,
    });
    setGoal("");
  }

  // Mark unavailable engines
  const availableSet = new Set(
    (engines ?? []).filter((e) => e.available).map((e) => e.engine_type),
  );

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="flex gap-3">
        <Textarea
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="Describe your goal..."
          rows={1}
          className="flex-1 resize-none text-sm"
          disabled={disabled}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              handleSubmit(e);
            }
          }}
        />
        <Button
          type="submit"
          disabled={disabled || !goal.trim()}
          size="sm"
        >
          Execute
        </Button>
      </div>

      {/* Engine selector */}
      <Collapsible open={showAdvanced} onOpenChange={setShowAdvanced}>
        <div className="flex items-center gap-2 flex-wrap">
          {ENGINE_OPTIONS.map((opt) => {
            const isAvailable = opt.value === "" || availableSet.has(opt.value) || availableSet.size === 0;
            const isSelected = engine === opt.value;
            const isFree = opt.value === "ollama" || opt.value === "";

            return (
              <Button
                key={opt.value}
                type="button"
                variant="outline"
                size="xs"
                disabled={!isAvailable && opt.value !== ""}
                onClick={() => setEngine(opt.value)}
                className={cn(
                  "gap-1.5 font-mono",
                  isSelected && "border-accent bg-accent/10 text-accent",
                  !isAvailable && opt.value !== "" && "opacity-30 cursor-not-allowed",
                )}
              >
                {isAvailable && opt.value !== "" && (
                  <CheckCircle2 size={10} className="text-success" />
                )}
                {!isAvailable && opt.value !== "" && (
                  <XCircle size={10} className="text-danger" />
                )}
                <span>{opt.label}</span>
                {isFree && isAvailable && (
                  <Badge variant="free" className="px-1 py-0 text-[8px]">FREE</Badge>
                )}
              </Button>
            );
          })}

          {/* Advanced toggle */}
          <CollapsibleTrigger
            className="ml-auto inline-flex items-center justify-center gap-1 whitespace-nowrap rounded px-2 text-xs font-medium font-mono text-text-muted transition-colors hover:bg-accent/10 hover:text-foreground h-6"
          >
            Advanced
            {showAdvanced ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </CollapsibleTrigger>
        </div>

        {/* Per-task fractal overrides */}
        <CollapsibleContent>
          <Card className="mt-3 bg-surface/50">
            <CardContent className="p-3">
              <p className="text-xs text-text-muted mb-2">
                Per-task fractal overrides (leave blank for global defaults)
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <label className="space-y-1">
                  <span className="text-xs text-text-muted">Max Depth</span>
                  <Input
                    type="number"
                    min={1}
                    max={10}
                    placeholder="default"
                    value={fractalDepth ?? ""}
                    onChange={(e) =>
                      setFractalDepth(e.target.value ? Number(e.target.value) : null)
                    }
                    className="h-7"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-xs text-text-muted">Max Concurrent</span>
                  <Input
                    type="number"
                    min={0}
                    max={50}
                    placeholder="default"
                    value={fractalConcurrency ?? ""}
                    onChange={(e) =>
                      setFractalConcurrency(e.target.value ? Number(e.target.value) : null)
                    }
                    className="h-7"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-xs text-text-muted">Throttle (ms)</span>
                  <Input
                    type="number"
                    min={0}
                    max={10000}
                    step={100}
                    placeholder="default"
                    value={fractalDelay ?? ""}
                    onChange={(e) =>
                      setFractalDelay(e.target.value ? Number(e.target.value) : null)
                    }
                    className="h-7"
                  />
                </label>
              </div>
            </CardContent>
          </Card>
        </CollapsibleContent>
      </Collapsible>
    </form>
  );
}
