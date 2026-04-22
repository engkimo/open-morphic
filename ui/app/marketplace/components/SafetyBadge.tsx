"use client";

const TIER_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  verified: { bg: "bg-emerald-900/50", text: "text-emerald-400", label: "VERIFIED" },
  community: { bg: "bg-cyan-900/50", text: "text-cyan-400", label: "COMMUNITY" },
  experimental: { bg: "bg-yellow-900/50", text: "text-yellow-400", label: "EXPERIMENTAL" },
  unsafe: { bg: "bg-red-900/50", text: "text-red-400", label: "UNSAFE" },
};

interface SafetyBadgeProps {
  tier: string;
  score?: number;
}

export default function SafetyBadge({ tier, score }: SafetyBadgeProps) {
  const style = TIER_STYLES[tier] || TIER_STYLES.experimental;

  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${style.bg} ${style.text}`}
      >
        {style.label}
      </span>
      {score !== undefined && (
        <span className="text-xs text-text-muted">{score.toFixed(2)}</span>
      )}
    </span>
  );
}
