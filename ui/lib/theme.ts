/** Morphic-Agent design tokens — "Mission Control for Intelligence" */

export const theme = {
  colors: {
    background: "#F4F1EA",
    surface: "#FBF9F3",
    border: "#E3DED2",
    accent: "#C15F3C",
    success: "#4F7A52",
    warning: "#B9821F",
    danger: "#C0492F",
    info: "#3B7A99",
    localFree: "#4F7A52",
    text: "#33312B",
    textMuted: "#7A776E",
  },
} as const;

export const statusStyles: Record<string, { border: string; icon: string }> = {
  pending: { border: "#C8C2B2", icon: "\u23F3" },
  running: { border: "#3B7A99", icon: "\u26A1" },
  success: { border: "#4F7A52", icon: "\u2713" },
  failed: { border: "#C0492F", icon: "\u2717" },
  fallback: { border: "#B9821F", icon: "\u21BB" },
};
