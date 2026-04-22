---
name: laee-dry-run
description: Preview a LAEE action plan — classify risk, check undo availability, inspect credential touchpoints — without executing anything.
when_to_use: Before approving a batch of LAEE actions in full-auto mode, or when the user wants to understand what would happen if they said yes.
argument-hint: "[plan-id | inline action list]"
allowed-tools:
  - Read
  - Grep
  - Glob
model: sonnet
---

# LAEE Dry Run

You simulate a LAEE plan's execution without side effects. Hands-off preview.

## Input

Either:
- A plan_id pointing to a persisted `ActionPlan` in `.morphic/plans/<id>.json`.
- An inline list of actions from `$ARGUMENTS`.

## Procedure

1. Load the action list.
2. For each action:
   - Classify risk via `domain/services/risk_assessor.py` logic (read only).
   - Check declared `LOCAL_TOOLS` risk level — flag mismatches.
   - Check credential path touchpoints: `~/.ssh/*`, `~/.aws/*`, `.env*`, `id_rsa*`, `*.pem`.
   - Check undo availability (tool's `reversible` flag + undo_hint).
   - Simulate approval decision per current `LAEE_APPROVAL_MODE` (from `.claude/settings.json` env).
3. Delegate edge cases to `local-safety-gate` subagent.
4. Produce preview.

## Output

```
# LAEE Dry Run — <plan_id>

## Mode
- Current: confirm-destructive (from settings.json)

## Actions
| # | Tool | Risk | Approval | Reversible | Credential? |
|---|---|---|---|---|---|
| 1 | shell_exec | MEDIUM | auto | yes | no |
| 2 | fs_delete  | HIGH   | prompt | YES (trash) | no |
| 3 | dev_git    | MEDIUM | auto | no | no |

## Summary
- 3 actions
- 1 will prompt user (HIGH)
- 0 credential touchpoints
- All reversible except #3

## Verdict
SAFE_TO_PROCEED / NEEDS_REVIEW / BLOCK

## Risk breakdown
- SAFE: 0 | LOW: 0 | MEDIUM: 2 | HIGH: 1 | CRITICAL: 0
```

## Guardrails

- **Absolutely no execution.** This is pure simulation.
- If any action is unclassified, block with "UNKNOWN RISK" rather than assuming.
- If the plan touches >50 files, require user to approve preview output before proceeding.
