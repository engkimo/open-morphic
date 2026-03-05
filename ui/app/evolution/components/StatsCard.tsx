"use client";

interface StatsCardProps {
  label: string;
  value: string;
  sub?: string;
  color?: string;
}

export default function StatsCard({ label, value, sub, color }: StatsCardProps) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <p className="text-xs text-text-muted">{label}</p>
      <p className={`mt-1 text-2xl font-bold ${color || "text-foreground"}`}>
        {value}
      </p>
      {sub && <p className="mt-0.5 text-xs text-text-muted">{sub}</p>}
    </div>
  );
}
