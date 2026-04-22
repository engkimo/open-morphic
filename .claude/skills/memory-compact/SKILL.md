---
name: memory-compact
description: Trigger ContextZipper compression on Morphic-Agent's L1-L4 semantic memory. Compacts old episodic entries, promotes frequently-accessed facts.
when_to_use: When semantic memory hits the Ebbinghaus forgetting threshold, when L1 context zipper ratio drops below 0.5, or proactively before long-running tasks.
argument-hint: "[--layer L1|L2|L3|L4|all] [--dry-run]"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(morphic memory compact *)
  - Bash(morphic memory stats *)
model: sonnet
---

# Memory Compact

You orchestrate compression of Morphic's semantic memory hierarchy.

## Memory layers

| Layer | Scope | Default retention |
|---|---|---|
| L1 | Working / current task | session |
| L2 | Session summary | 7 days |
| L3 | Episodic / task logs | 30 days |
| L4 | Semantic / distilled knowledge | indefinite |

## Procedure

1. Read `$ARGUMENTS` for `--layer` and `--dry-run`.
2. Delegate to `memory-archaeologist` subagent to check stats:
   ```bash
   morphic memory stats --json
   ```
3. For each requested layer:
   - L1: trim to top-K by recency × salience (ContextZipper).
   - L2: merge redundant summaries via LLM distillation.
   - L3: apply Ebbinghaus forgetting curve (half-life 7 days).
   - L4: re-index LSH, prune fingerprints with zero hits >90 days.
4. If `--dry-run`, report projected compression ratio without writing.
5. Otherwise, run:
   ```bash
   morphic memory compact --layer <L> --execute
   ```
6. Verify post-stats match expected ratio.

## Output

```
# Memory Compact — <date>

## Before
- L1: 142 entries, 98 KB
- L2: 38 entries, 210 KB
- L3: 1,204 entries, 4.1 MB
- L4: 18,422 fingerprints, 45 MB

## After
- L1: 32 entries, 22 KB (0.22× )
- L2: 12 entries, 68 KB (0.32×)
- L3: 942 entries, 2.8 MB (0.68×)
- L4: 16,108 fingerprints, 38 MB (0.84×)

## Retained in L4 (promoted from L3)
- <N> patterns
```

## Guardrails

- **Never delete unread.** Anything not yet surfaced to user must be promoted, not dropped.
- L4 semantic fingerprints are append-only — prune only by hit-count + age.
- If compression ratio >0.95 (barely compressed), investigate before re-running.
- Abort if `morphic memory stats` reports corruption.
