/** Morphic-Agent design tokens — "Mission Control for Intelligence" */

export const theme = {
  colors: {
    background: "#0A0A0F",
    surface: "#12121A",
    border: "#1E1E2E",
    accent: "#6366F1",
    success: "#10B981",
    warning: "#F59E0B",
    danger: "#EF4444",
    info: "#38BDF8",
    localFree: "#34D399",
    text: "#E2E8F0",
    textMuted: "#94A3B8",
  },
} as const;

export const statusStyles: Record<string, { border: string; icon: string }> = {
  pending: { border: "#2D2D42", icon: "\u23F3" },
  running: { border: "#38BDF8", icon: "\u26A1" },
  success: { border: "#10B981", icon: "\u2713" },
  failed: { border: "#EF4444", icon: "\u2717" },
  fallback: { border: "#F59E0B", icon: "\u21BB" },
};
