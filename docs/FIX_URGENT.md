# Urgent Fix Plan — Based on Live Log Analysis (2026-03-20)

> This document is a direct instruction set for implementation.
> Fix in order. Each fix must be verified before moving to the next.

## Progress

| Fix | Description | Status | Commit | Notes |
|-----|-------------|--------|--------|-------|
| Fix 1 | Suppress log noise | ✅ DONE | `c2df917` | Added `sqlalchemy.engine`, `sqlalchemy.pool` to suppression list |
| Fix 2 | Fix web_search | ✅ DONE | `422bfa1` | DuckDuckGo HTML endpoint blocked (bot detection). Switched to `ddgs` package. HTML parsing kept as fallback |
| Fix 3 | ReAct empty results | ✅ DONE | `1da6f72` | `_build_fallback_answer()` preserves last 3 observations when max_iterations hit |
| Fix 4 | Multi-model execution | ✅ DONE | `de192b8` | 3 bugs: env vars not exported, GEMINI_API_KEY mapping, availability guard skipped explicit models |
| Fix 5 | UI subtask detail | ✅ DONE | `d473425` | 6 TS fields added, expandable detail with result/tools/sources/cost |
| Fix 6 | Final output display | ✅ DONE | `8e1d368` | Combined result section for success, error summary for failed |

---

## Context: What the logs revealed

Running `"gptとgemini,claudeと一緒に、今週土曜のゴジュウジャーの映画チケットの一番安い映画館を埼玉で探して。"` produced:

```
ReAct tool — step=9 tool=web_search obs_len=17     ← web_search returns only 17 chars
ReAct stopped — step=9 reason=max_iterations        ← LLM loops 10x, never produces answer
Subtask d0ab1cc5 (ReAct) — model=ollama/qwen3:8b   ← Still Ollama, not GPT/Gemini/Claude
"result": ""                                         ← Empty result stored in DB
```

The SQLAlchemy engine logs flood the terminal (duplicate output from structlog + stdlib), making debugging impossible.

---

## Fix 1: Suppress log noise (5 min) ✅ DONE

**Problem**: SQLAlchemy logs every SELECT/COMMIT at INFO level, duplicated (structlog + stdlib). WebSocket polls every 1s = 4+ log lines/sec of noise.

**File**: `shared/logging.py`

**Action**: In `setup_logging()`, add these loggers to the suppression list:

```python
# Suppress noisy loggers
for name in [
    "httpx", "httpcore", "litellm", "urllib3", "asyncio",
    "sqlalchemy.engine",       # ← ADD: stop SQL query spam
    "sqlalchemy.engine.Engine", # ← ADD: stop duplicate engine logs
    "sqlalchemy.pool",          # ← ADD
]:
    logging.getLogger(name).setLevel(logging.WARNING)
```

**Verify**: Restart server, trigger a task. Terminal should show only morphic-agent logs, not SQL queries.

---

## Fix 2: Verify and fix web_search (15 min) ✅ DONE

**Problem**: `web_search` returns `obs_len=17` which is likely `"No results found."` or a short error. DuckDuckGo HTML endpoint may be blocking automated requests.

**File**: `infrastructure/local_execution/tools/web_tools.py`

**Action**:

1. Add a manual test first — run in Python REPL:
```python
import asyncio
from infrastructure.local_execution.tools.web_tools import web_search
result = asyncio.run(web_search({"query": "ゴジュウジャー 映画 埼玉"}))
print(repr(result))
print(f"len={len(result)}")
```

2. If DuckDuckGo is blocked, the `_parse_ddg_results` regex may not match the updated HTML structure. Check:
   - Is `resp.status_code` 200?
   - Does the HTML contain `class="result__a"` or has DuckDuckGo changed its class names?
   - Try with an English query to rule out encoding issues.

3. If DuckDuckGo HTML parsing is broken, switch to a more reliable approach:
   - Option A: Use `duckduckgo-search` pip package (`pip install duckduckgo-search`)
   - Option B: Use SearXNG if available
   - Option C: Fall back to a simple `httpx` GET to a search API

4. After fix, verify the same REPL test returns 5+ results with URLs and snippets.

**Verify**: `web_search({"query": "movie tickets Saitama"})` returns real results with URLs.

---

## Fix 3: Handle ReAct max_iterations — no empty results (10 min) ✅ DONE

**Problem**: When ReAct hits `max_iterations`, `trace.final_answer` is empty. The subtask gets `result=""`. The UI shows nothing.

**File**: `infrastructure/task_graph/react_executor.py`

**Action**: In `execute()`, after the for-loop, if `trace.final_answer` is empty, construct a fallback answer from the observations collected during the loop:

```python
# After the for-loop (line ~146)
if not trace.final_answer:
    # Collect tool observations as fallback
    all_observations = []
    for step in trace.steps:
        all_observations.extend(step.observations)
    if all_observations:
        trace.final_answer = (
            "Tool results (max iterations reached):\n"
            + "\n---\n".join(all_observations[-3:])  # last 3 observations
        )
    else:
        trace.final_answer = "No results obtained within iteration limit."
    trace.terminated_reason = "max_iterations"
```

Also in `infrastructure/task_graph/engine.py`, in the ReAct path inside `execute_one()`, after getting the result, check for max_iterations and set status appropriately:

```python
if result.trace.terminated_reason == "max_iterations":
    subtask.status = SubTaskStatus.SUCCESS  # or DEGRADED if you added it
    # Ensure result is not empty
    if not result.final_answer.strip():
        subtask.result = "Task could not be completed within iteration limit."
```

**Verify**: Run a task → even if ReAct loops out, subtask has non-empty result text.

---

## Fix 4: Multi-model execution — use cloud models when requested (30 min)

**Problem**: User says "gptとgemini,claudeで" but all subtasks run on `ollama/qwen3:8b`. The `ModelPreferenceExtractor` detects models and sets `preferred_model`, but execution doesn't respect it.

**Diagnosis steps** (check these in order):

### 4a. Verify ModelPreferenceExtractor works

```python
from domain.services.model_preference_extractor import ModelPreferenceExtractor
pref = ModelPreferenceExtractor.extract(
    "gptとgemini,claudeと一緒に、今週土曜のゴジュウジャーの映画チケットの一番安い映画館を埼玉で探して。"
)
print(pref.models)        # Should be ("o4-mini", "gemini/...", "claude-sonnet-4-6")
print(pref.is_multi_model) # Should be True
print(pref.clean_goal)     # Should be clean Japanese without model names
```

### 4b. Verify IntentAnalyzer takes multi-model path

In `infrastructure/task_graph/intent_analyzer.py`, add a debug log at the top of `decompose()`:

```python
logger.info("ModelPreference: models=%s multi=%s mode=%s",
            preference.models, preference.is_multi_model, preference.collaboration_mode)
```

Check that when the task runs, the log shows `multi=True`.

### 4c. Verify preferred_model reaches LLM gateway

In `infrastructure/task_graph/engine.py`, in `execute_one()`, log the model being used:

```python
logger.info("Subtask %s — preferred_model=%s", subtask_id, subtask.preferred_model)
```

### 4d. Fix LiteLLMGateway model resolution

In `infrastructure/llm/litellm_gateway.py`, the `complete()` method:

```python
resolved = model or self._default_free_model
```

If `model="o4-mini"` is passed, it should use it directly. But check:
- Is `OPENAI_API_KEY` valid? If not, the call will fail.
- For Gemini: is `GOOGLE_GEMINI_API_KEY` set? LiteLLM needs it as env var `GEMINI_API_KEY`.
- The `complete_with_tools()` method has the same pattern — verify both.

### 4e. Fix: cloud model errors should not fail silently

In `LiteLLMGateway.complete()` and `complete_with_tools()`, API errors (401, rate limit, etc.) will raise exceptions. In `engine.py execute_one()`, these are caught by the generic `except Exception` and treated as retries. After 2 retries, the subtask fails.

**But the current behavior might silently fall back to Ollama instead of reporting the error.**

Check if there's any fallback logic that changes the model. If so, log it clearly:

```python
logger.warning("Cloud model %s failed, NO automatic fallback to Ollama — task will fail", model)
```

### 4f. Set GEMINI_API_KEY env var for LiteLLM

LiteLLM expects `GEMINI_API_KEY` (not `GOOGLE_GEMINI_API_KEY`). Check `.env` and `shared/config.py`:

In `interface/api/main.py` (or `container.py`), ensure:
```python
import os
if settings.google_gemini_api_key:
    os.environ["GEMINI_API_KEY"] = settings.google_gemini_api_key
```

**Verify**: Trigger "gptとclaudeで1+1は？" → one subtask uses o4-mini, another uses claude-sonnet-4-6.

---

## Fix 5: UI — Show subtask detail logs (20 min)

**Problem**: UI shows subtask description and model, but no:
- Tool calls made
- ReAct iterations
- Actual result text
- Error messages

**Files**: `ui/components/TaskDetail.tsx`, `ui/lib/api.ts`, `interface/api/schemas.py`

### 5a. Backend: include new fields in API response

In `interface/api/schemas.py`, `SubTaskResponse`:

```python
class SubTaskResponse(BaseModel):
    id: str
    description: str
    status: str
    result: str | None = None          # ← ensure this exists
    error: str | None = None           # ← ensure this exists
    model_used: str | None = None
    cost_usd: float = 0.0
    code: str | None = None
    execution_output: str | None = None
    complexity: str | None = None
    tool_calls_count: int = 0          # ← ADD if missing
    react_iterations: int = 0          # ← ADD if missing
    tools_used: list[str] = []         # ← ADD if missing
    engine_used: str | None = None     # ← ADD if missing
    preferred_model: str | None = None # ← ADD if missing
```

### 5b. Frontend: expandable subtask detail

In `ui/components/TaskDetail.tsx`, make each subtask row expandable (click to expand). When expanded, show:

```tsx
{/* Expanded subtask detail */}
{expanded === st.id && (
  <div className="mt-2 p-3 bg-surface rounded border border-border text-sm space-y-2">
    {st.result && (
      <div>
        <span className="text-textMuted">Result:</span>
        <pre className="mt-1 whitespace-pre-wrap text-text">{st.result}</pre>
      </div>
    )}
    {st.error && (
      <div className="text-danger">
        <span>Error:</span> {st.error}
      </div>
    )}
    {st.react_iterations > 0 && (
      <div className="text-textMuted">
        ReAct: {st.react_iterations} iterations, {st.tool_calls_count} tool calls
        {st.tools_used?.length > 0 && ` (${st.tools_used.join(", ")})`}
      </div>
    )}
    {st.preferred_model && st.preferred_model !== st.model_used && (
      <div className="text-warning">
        Requested: {st.preferred_model} → Actual: {st.model_used}
      </div>
    )}
  </div>
)}
```

### 5c. Frontend: update TypeScript types

In `ui/lib/api.ts`, update the `SubTask` interface:

```typescript
interface SubTask {
  id: string;
  description: string;
  status: string;
  result?: string;
  error?: string;
  model_used?: string;
  cost_usd: number;
  code?: string;
  execution_output?: string;
  complexity?: string;
  tool_calls_count?: number;
  react_iterations?: number;
  tools_used?: string[];
  engine_used?: string;
  preferred_model?: string;
}
```

**Verify**: Click on a subtask → see result text, tool calls count, iterations, errors.

---

## Fix 6: Show final output on task detail page (10 min)

**Problem**: Task detail page shows subtasks but not the combined final answer.

**File**: `ui/app/tasks/[id]/page.tsx`

**Action**: After the subtasks list, add a "Final Output" section that combines all successful subtask results:

```tsx
{/* Final Output */}
{task.status === "success" && (
  <div className="mt-6 p-4 bg-surface rounded border border-border">
    <h3 className="text-lg font-semibold text-text mb-2">Final Output</h3>
    <div className="whitespace-pre-wrap text-text">
      {task.subtasks
        .filter((st: SubTask) => st.status === "success" && st.result)
        .map((st: SubTask) => st.result)
        .join("\n\n---\n\n")}
    </div>
  </div>
)}
{task.status === "failed" && (
  <div className="mt-6 p-4 bg-surface rounded border border-danger/30">
    <h3 className="text-lg font-semibold text-danger mb-2">Errors</h3>
    <div className="whitespace-pre-wrap text-text">
      {task.subtasks
        .filter((st: SubTask) => st.error)
        .map((st: SubTask) => `${st.description}: ${st.error}`)
        .join("\n\n")}
    </div>
  </div>
)}
```

**Verify**: Completed task → "Final Output" section shows combined results.

---

## Execution Order

```
Fix 1 (log noise)         →  5 min   →  ✅ DONE (c2df917)
Fix 2 (web_search)        → 15 min   →  ✅ DONE (422bfa1)
Fix 3 (empty results)     → 10 min   →  ✅ DONE (1da6f72)
Fix 4 (multi-model)       → 30 min   →  ✅ DONE
Fix 5 (UI subtask detail) → 20 min   →  ✅ DONE
Fix 6 (final output)      → 10 min   →  ✅ DONE
```

## Test Command After All Fixes

```bash
# Simple multi-model test (fast, cheap)
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"goal": "gptとclaudeで、1+1を計算して"}'

# Expected:
# - 2 subtasks: one with model_used=o4-mini, one with model_used=claude-sonnet-4-6
# - Both have non-empty results
# - UI shows expandable subtask details
# - Final Output section shows both answers
```

```bash
# Full web search test (slower, real-world)
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"goal": "geminiで東京の天気を検索して"}'

# Expected:
# - web_search tool called with real results
# - Result contains actual weather data or URLs
# - tools_used: ["web_search"]
# - react_iterations > 0
```

---

## ALL FIXES COMPLETE (2026-03-20)

All 6 fixes from the live log analysis have been implemented and pushed.

### Summary of Changes

| Fix | Files Changed | Root Cause |
|-----|---------------|------------|
| Fix 1 | `shared/logging.py` | SQLAlchemy loggers at INFO level flooding terminal |
| Fix 2 | `infrastructure/local_execution/tools/web_tools.py` | DuckDuckGo HTML endpoint blocking bots; switched to `ddgs` package |
| Fix 3 | `infrastructure/task_graph/react_executor.py`, `engine.py` | No fallback answer when ReAct hits max_iterations |
| Fix 4 | `interface/api/main.py`, `infrastructure/llm/litellm_gateway.py`, tests | pydantic-settings doesn't export to os.environ; GEMINI_API_KEY mismatch; `model is None` guard skipped availability check for explicit models |
| Fix 5 | `interface/api/schemas.py`, `ui/lib/api.ts`, `ui/components/TaskDetail.tsx` | TS interface missing 6 fields; no expandable detail section |
| Fix 6 | `ui/components/TaskDetail.tsx` | No combined Final Output or Error summary on task detail page |

### Test Results After All Fixes

- **1930 unit tests**: All pass (was 1928 before Fix 4 added 2 new tests)
- **Lint**: Clean (ruff check)
- **Format**: Clean (ruff format)

### What's Next

FIX_URGENT is done. Remaining work from `FIX_PLAN.md`:
- **Live verification**: Run the test commands above to confirm end-to-end
- **Deeper integration**: FIX_PLAN.md Section 4 gaps (RouteToEngineUseCase in DAG, discussion phase, MCP in ReAct, smart success validation) are architectural improvements beyond urgent fixes
