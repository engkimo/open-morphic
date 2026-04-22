/** Graph layout utilities — depth-based DAG positioning. */

import type { SubTaskResponse } from "./api";

/**
 * Compute the depth (column) for each subtask based on dependency chains.
 * Root nodes (no deps) get depth 0. Each dependent gets max(parent depths) + 1.
 */
export function computeNodeDepths(
  subtasks: SubTaskResponse[],
): Map<string, number> {
  const depthMap = new Map<string, number>();
  const idSet = new Set(subtasks.map((s) => s.id));

  function getDepth(id: string, visited: Set<string>): number {
    if (depthMap.has(id)) return depthMap.get(id)!;
    if (visited.has(id)) return 0; // cycle guard
    visited.add(id);

    const st = subtasks.find((s) => s.id === id);
    if (!st || st.dependencies.length === 0) {
      depthMap.set(id, 0);
      return 0;
    }

    const maxParent = Math.max(
      ...st.dependencies
        .filter((d) => idSet.has(d))
        .map((d) => getDepth(d, visited)),
      -1,
    );
    const depth = maxParent + 1;
    depthMap.set(id, depth);
    return depth;
  }

  for (const st of subtasks) {
    getDepth(st.id, new Set());
  }
  return depthMap;
}

/**
 * Compute dynamic graph container height based on subtask count.
 * min 300px, max 700px.
 */
export function computeGraphHeight(subtaskCount: number): number {
  return Math.max(300, Math.min(700, subtaskCount * 110 + 100));
}

/**
 * Truncate text with ellipsis if it exceeds maxLen.
 */
export function truncateWithEllipsis(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen - 1) + "\u2026";
}
