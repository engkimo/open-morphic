import { useEffect } from "react";

/**
 * Auto-refresh hook: polls at `intervalMs` when `active` is true.
 *
 * TD-170: Adds auto-refresh to Dashboard, Cost, and Engines pages
 * when tasks are running/pending.
 */
export function useAutoRefresh(
  refresh: () => void,
  active: boolean,
  intervalMs: number = 3000,
) {
  useEffect(() => {
    if (!active) return;
    const id = setInterval(refresh, intervalMs);
    return () => clearInterval(id);
  }, [refresh, active, intervalMs]);
}
