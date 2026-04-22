---
name: engine-e2e
description: Run live end-to-end verification across Morphic-Agent's 6 agent CLI engines. Produces a baseline comparison table with duration and cost per engine.
when_to_use: When the user asks for an "E2E round", "live test", "engine check", or "smoke test".
argument-hint: "[engines | all]"
allowed-tools:
  - Bash
  - Read
  - Grep
model: sonnet
---

# Engine E2E Runner

Runs the canonical smoke task against each available engine and produces a comparison report.

## Usage

```
/engine-e2e            # all engines
/engine-e2e ollama     # single engine
/engine-e2e claude,codex,gemini  # multiple
```

Argument: `$ARGUMENTS`

## Canonical smoke task

`"Return the sum 2+2 as a single number."`

Expected output: exactly `4` (or `4.` / `"4"` depending on engine format).

## Procedure

1. Delegate to the `engine-tester` subagent with the engine list from `$ARGUMENTS`.
2. The subagent runs each engine in a forked context (keeps noise out of main log).
3. Collect its report.
4. Append a one-line entry to `docs/CONTINUATION.md` under "Live Verification Summary":

   ```
   - **Round NN** (<date>): <description>, N/M engines passing, $X.XX
   ```

5. If any engine regressed vs the last known-good baseline, flag it.

## Baselines (known-good)

| Engine | Duration | Cost | Source |
|---|---|---|---|
| Ollama (qwen3:8b) | ~1-3s | $0.00 | Round 17 |
| Claude Code SDK | ~3-5s | ~$0.01 | Round 15 (via routing) |
| Codex CLI | ~40-50s | ~$0.02 | Round 15 |
| Gemini CLI | ~2-5s | ~$0.001 | Round 18 |
| OpenHands (Gemini) | ~30-60s | ~$0.005 | Round 16 |
| Fractal (hybrid) | ~5-10s | ~$0.024 | Round 17 |

## Output

Table + summary + delta vs baseline. Store in `docs/CONTINUATION.md`.

## Guardrails

- **Budget cap**: total run must stay under $0.50. Abort if projected cost exceeds.
- **Never** include credentials in test prompts.
- Flag engines that take >2× baseline duration.
