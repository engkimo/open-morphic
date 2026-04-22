---
name: cost-report
description: Generate a monthly or on-demand cost report across LLM providers, local LLMs, and agent engines. Flags overspend and suggests downgrades.
when_to_use: When user asks about spending, at month boundary, or when budget circuit breaker approaches 80%.
argument-hint: "[period: today|week|month|YYYY-MM]"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(morphic cost report *)
  - Bash(sqlite3 * SELECT*)
model: sonnet
---

# Cost Report

You produce an actionable cost report.

## Input

`$ARGUMENTS` = period (default: current month).

## Procedure

1. Delegate to `cost-guardian` subagent.
2. The subagent queries:
   - LiteLLM callback costs (primary ledger).
   - `infrastructure/persistence/*/cost_records.py` (persisted aggregates).
   - Ollama local inference token counts (for shadow cost = $0).
3. Aggregate by:
   - Provider (Anthropic, OpenAI, Google, Ollama).
   - Engine (Claude Code, Codex, Gemini, OpenHands, Ollama, Fractal).
   - Task category (SIMPLE / COMPLEX, via bypass classifier tag).
   - Top 10 most expensive tasks.
4. Compute:
   - **LOCAL rate** = `ollama_tokens / total_tokens` × 100%.
   - **Cache hit rate** = `cached_tokens / input_tokens` × 100%.
   - **Budget used** = `month_to_date / monthly_cap` × 100%.
5. Generate downgrade ladder if budget >80%: e.g. "move o4-mini → qwen3:8b for SIMPLE tasks (projected -$1.20)".

## Output

```
# Cost Report — <period>

## Summary
- Total: $X.XX
- Budget: $Y.YY (N% used)
- LOCAL rate: NN%
- Cache hit rate: NN%

## By provider
| Provider | Tokens in | Tokens out | Cost |
|---|---|---|---|
| anthropic | 1.2M | 340k | $4.20 |
| google    | 800k | 210k | $0.15 |
| openai    | 50k  | 12k  | $0.80 |
| ollama    | 2.1M | 580k | $0.00 |

## By engine
(same format)

## Top 10 tasks by cost
1. task_7f3a... $1.20 (complex plan, Claude Sonnet)
2. ...

## Alerts
- ⚠️ 3 tasks exceeded $0.50 individual cap
- ⚠️ Cache hit rate dropped from 62% to 48% this week

## Suggested actions
- Raise LOCAL rate from 72% → 85% by routing all SIMPLE to ollama (est. -$X/mo)
- Enable prompt caching for /fractal-analyze (est. -$Y/mo)
```

## Guardrails

- Never include API keys or full prompts in the report.
- If budget >95%, emit a CRITICAL line — circuit breaker may fire.
- Always cite the exact query/time range used.
