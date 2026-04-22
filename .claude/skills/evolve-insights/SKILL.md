---
name: evolve-insights
description: Extract session insights after a task completes and feed them into Morphic's self-evolution engine. Captures what worked, what didn't, and proposes prompt/routing tweaks.
when_to_use: After completing a non-trivial task. Also on `/loop` boundary to run evolution continuously.
argument-hint: "[session_id | last]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - Bash(morphic session export *)
model: sonnet
---

# Evolve Insights

You harvest learnings from a completed session and route them to the evolution engine.

## Input

`$ARGUMENTS` = session id (default: last).

## Procedure

1. Export the session timeline:
   ```bash
   morphic session export <id> --format json > /tmp/session.json
   ```
2. Delegate analysis to `harness-optimizer` subagent.
3. The subagent classifies each step into:
   - **WIN**: went faster/cheaper than baseline. Capture the pattern.
   - **LOSS**: regression, retry, or extra-cost path.
   - **SURPRISE**: unexpected behavior (good or bad).
4. For each WIN:
   - Distill to a portable rule (model/prompt/route hint).
   - Store in `evolution/wins.jsonl` as an append-only record.
5. For each LOSS:
   - Identify the proximate cause (prompt, model, tool, classifier).
   - Draft a counter-measure (prompt patch, routing weight shift, new tool).
   - Store in `evolution/losses.jsonl`.
6. Output a session postmortem.
7. If ≥3 losses of the same kind, propose a harness change and stop — user decides whether to apply.

## Output

```
# Evolve Insights — session <id>

## Wins (N)
- W-01 bypass classifier skipped 3 subtasks correctly, saved $0.04
- W-02 Gemini CLI beat Claude on structured extraction, 2.3s vs 4.1s

## Losses (N)
- L-01 fractal planner over-split a 2+2 task into 5 nodes (TD-167 regression)
- L-02 OpenHands retry after temperature error — use Gemini engine instead

## Surprises (N)
- S-01 ollama qwen3:8b matched Sonnet quality on JSON extraction

## Proposed harness changes
1. Tighten bypass threshold for arithmetic tasks (+confidence weight 0.2)
2. Blacklist OpenHands+Claude until OH upgrade

## Recommendation
Apply #1 immediately (low risk, reversible). Defer #2 until next release.
```

## Guardrails

- Never auto-apply harness changes. Always require user approval.
- Preserve raw session data — evolution entries are derivative, not replacements.
- If ≥3 losses share a root cause, escalate to user before adding more detections.
