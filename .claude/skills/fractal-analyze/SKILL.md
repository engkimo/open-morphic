---
name: fractal-analyze
description: Inspect Morphic-Agent's fractal task graph for a given task_id. Reports bypass classifier decisions, Gate 2 skips, parallelism, and regression flags.
when_to_use: When debugging why a task took too long, cost too much, or was misclassified. Also for post-mortem analysis.
argument-hint: "<task_id>"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(morphic task inspect *)
  - Bash(sqlite3 * SELECT*)
model: sonnet
---

# Fractal Analyze

You produce a forensic report on a task's fractal execution.

## Input
Task ID via `$ARGUMENTS` (required).

## Procedure

1. Delegate to `fractal-analyst` subagent with the task_id.
2. The subagent:
   - Loads the task graph from persistence.
   - Inspects bypass classifier decision + prompt.
   - Walks the tree, noting Gate 2 skips.
   - Identifies parallel groups.
3. Cross-reference TD-167 (bypass), TD-168 (Gate 2 skip), TD-169 (parallel nodes), TD-181 (timeout) from `docs/TECH_DECISIONS.md`.
4. Produce the report.

## Output

See `fractal-analyst` agent for format. Additionally:

- Cross-link to relevant ADRs (TD-xxx).
- If regression detected, suggest opening a GitHub issue with template.

## Known patterns to flag

- **Zombie task**: task_id alive > 5 minutes with no progress → TD-181 timeout should have fired.
- **Over-bypassed**: complex task classified SIMPLE, result quality low.
- **Gate 2 false-skip**: node success=true but output is empty string.
- **Parallel contention**: two nodes writing to same artifact path.

## Guardrails

- **Read-only.** Never re-run the task.
- Do not delete persisted graph data.
- If persistence backend is PG and `DATABASE_URL` not set, fall back to SQLite at `.morphic/morphic.db`.
