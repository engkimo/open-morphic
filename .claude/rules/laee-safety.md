---
paths:
  - infrastructure/local_execution/**
  - domain/services/risk_assessor.py
  - domain/services/approval_engine.py
---

# LAEE — Safety Rules

LAEE operates directly on the user's machine. Every change in this subtree is safety-critical.

## Must Always

1. **Every tool has an explicit risk level** (SAFE / LOW / MEDIUM / HIGH / CRITICAL). No defaults to "MEDIUM" — classify it.
2. **Every action is logged to `.morphic/audit_log.jsonl`** before execution starts, not after. If the process crashes, the intent is still recorded.
3. **Risk classification is separate from approval transport.** `risk_assessor.py` decides the level; `approval_engine.py` handles user interaction. Never combine them.
4. **Reversible actions populate the undo stack** (`LocalExecutor.undo_stack`).
5. **Read-only operations on `~/.ssh`, `~/.aws`, `.env*`, any `*.pem` / `*.key` / `id_rsa*`** are CRITICAL. Read **with caution** — writes are refused in all modes except explicit full-auto with a user banner.

## Must Never

- Never bypass `ApprovalEngine.check()` for destructive ops.
- Never weaken the `APPROVAL_MATRIX` table without a tested migration.
- Never make `full-auto` the default.
- Never add a new tool without declaring its risk level in `LOCAL_TOOLS`.
- Never log credentials or secret contents in `audit_log.jsonl` — hash or redact.

## Testing

- Every new tool ships with:
  - Unit test for `risk_assessor` classification.
  - Unit test for `ApprovalEngine` decision matrix.
  - Integration test in `confirm-destructive` mode that verifies prompt appears for HIGH/CRITICAL.
