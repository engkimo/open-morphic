---
name: constitution-check
description: Verify a feature spec, plan, or PR against the non-negotiable principles in `.specify/memory/constitution.md`.
when_to_use: As a gate between /prp-plan and /prp-implement. Also before merging any PR that touches domain/ or infrastructure/.
argument-hint: "[spec-slug | pr-number | path]"
allowed-tools:
  - Read
  - Grep
  - Glob
model: opus
---

# Constitution Check

You audit work against Morphic-Agent's 10 non-negotiable principles.

## Input

One of:
- `<slug>` → reads `specs/<slug>/plan.md` (preferred).
- `pr <N>` → reads staged diff for PR N via `gh pr diff`.
- `<path>` → reads a single file or directory.

## The 10 principles

Load `.specify/memory/constitution.md`. Each feature must satisfy:

1. **Local-First** — LOCAL_FIRST=true path exists; no API-only codepaths.
2. **Clean Architecture** — domain has zero infra deps; application uses ports, not impls.
3. **KV-Cache Stability** — system prompts are immutable prefixes; no timestamps at top.
4. **Safety (LAEE)** — new local actions declare risk level; credential paths blocked.
5. **TDD** — tests precede code; RED commit exists before GREEN.
6. **Spec-Driven** — spec → plan → tasks exist for non-trivial features.
7. **Cost Discipline** — cost budget declared; downgrade ladder exists.
8. **UCL** — cross-engine handoff preserves decisions/artifacts/blockers.
9. **Append-Only Context** — no in-place edits of past tool results.
10. **Evolve** — wins/losses feed `.morphic/evolution/` logs.

## Procedure

1. Load the target.
2. For each principle, produce: PASS / WARN / FAIL / N/A + evidence line.
3. If any FAIL, block and list remediation.
4. If ≥2 WARN, require user review.

## Output

```
# Constitution Check — <target>

| # | Principle | Status | Evidence |
|---|---|---|---|
| 1 | Local-First | PASS | plan.md:42 cites ollama path |
| 2 | Clean Arch | PASS | layer map in plan.md |
| 3 | KV-Cache | N/A | no prompt changes |
| 4 | LAEE Safety | WARN | new `fs_move` action — risk unset |
| 5 | TDD | PASS | tasks T-01..T-05 are RED |
| ... |

## Verdict
NEEDS REVISION (1 WARN on principle 4)

## Remediation
- Set `risk_level=MEDIUM` on fs_move in plan.md, wire through risk_assessor.py
```

## Guardrails

- Never override a FAIL. Escalate to user.
- "I think this is fine" is not evidence — cite a file:line.
- Block PR merges automatically on any FAIL (via git hook, not this skill).
