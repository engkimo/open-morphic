"use client";

import { useState } from "react";

interface GoalInputProps {
  onSubmit: (goal: string) => void;
  disabled?: boolean;
}

export default function GoalInput({ onSubmit, disabled }: GoalInputProps) {
  const [goal, setGoal] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = goal.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
    setGoal("");
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-3">
      <textarea
        value={goal}
        onChange={(e) => setGoal(e.target.value)}
        placeholder="Describe your goal..."
        rows={2}
        className="flex-1 resize-none rounded-lg border border-border bg-surface px-4 py-3 font-mono text-sm text-foreground placeholder:text-text-muted focus:border-accent focus:outline-none"
        disabled={disabled}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSubmit(e);
          }
        }}
      />
      <button
        type="submit"
        disabled={disabled || !goal.trim()}
        className="rounded-lg bg-accent px-6 py-3 font-mono text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-40"
      >
        Execute
      </button>
    </form>
  );
}
