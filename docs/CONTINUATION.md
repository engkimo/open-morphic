# Morphic-Agent — Continuation State

> Last updated: 2026-07-07
> Latest work: Morphic Chat CLI Phase 25 CLI permission mode controls

## Latest Session Notes (2026-06-26)

User direction:
- Build a first-party Morphic terminal chat CLI similar in UX to Claude Code, Gemini CLI, and Codex CLI.
- Do not make it just another single-engine CLI. Morphic should be the multi-engine, multi-agent control plane.
- Solve the real pain: users manually switch CLIs and manually sync memory, markdown instructions, hooks, harnesses, sessions, and metadata across `.claude/`, `AGENTS.md`, `GEMINI.md`, Codex config, etc.
- Use `claw-code` only as an operational feature catalog for good agent CLI behavior, not as an implementation source.

Artifacts added:
- `specs/morphic-chat-cli/spec.md`
- `specs/morphic-chat-cli/plan.md`
- `specs/morphic-chat-cli/tasks.md`
- `specs/morphic-chat-cli/operational-catalog.md`

Phase 1 implemented:
- Added chat domain entities: `ChatEvent`, `ChatSession`, `ContextIndex`, `ApprovalRequest` / `ApprovalDecision`, and council role/decision primitives.
- Added chat domain ports: `ChatSessionStorePort`, `ContextDiscoveryPort`, `CouncilRuntimePort`, `ToolExecutorPort`, and `EngineRegistryPort`.
- Added unit tests for strict Pydantic validation, append-only event sequencing, role/engine separation, tool risk classification, engine profiles, and Clean Architecture import boundaries.

Phase 2 implemented:
- Added application use cases for start/resume/send message/context discovery/slash commands/tool approval/session summary.
- Use cases append normalized `ChatEvent`s through `ChatSessionStorePort` and keep infrastructure concerns out of application code.
- Added unit tests with fake ports for event sequencing, resume reconstruction, council-to-event conversion, slash command handling, read-only status output, approvals, and summaries.

Phase 3 implemented:
- Added `JsonlChatSessionStore` for append-only `.morphic/sessions/<session_id>.jsonl` ledgers.
- Added `WorkspaceContextDiscovery` for read-only discovery of `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.claude/*`, `.morphic/context`, `.morphic/memory`, `.cursor/rules`, and GitHub Copilot instructions, plus `.morphic/context/index.json` generation.
- Added deterministic `LocalChatCouncilRuntime` and `StaticEngineRegistry` for MVP wiring before external CLI adapters are connected.

Phase 4 implemented:
- Added top-level `morphic chat` line-oriented REPL and `morphic code "<goal>"` one-shot command.
- Added slash command parser plus `/help`, `/status`, `/context`, `/engines`, `/diff`, and `/quit` handling through application use cases.
- Added `morphic chat --doctor --json` diagnostics and CLI tests that verify session JSONL ledgers are created.

Phase 5 implemented:
- Added chat tool execution use case with read-only mutation blocking and event sequencing for diff proposals, tool requests, tool completions, and verification results.
- Added LAEE-compatible `LaeeToolExecutor` adapter that converts chat `ToolExecutionRequest` values into LAEE `Action`s and normalizes `Observation`s back into chat tool results.
- Added approval prompt rendering for pending approval requests.

Phase 6 implemented:
- Added `morphic context scan` and `morphic context scan --json` to generate `.morphic/context/index.json` through the application context discovery use case.
- Added `morphic doctor agents` and `morphic doctor agents --json` for agent engine and optional CLI diagnostics.
- Switched chat/context/doctor JSON command output to `typer.echo` so machine-readable output is not wrapped by Rich console rendering.
- Stable non-interactive exit code policy: FAIL exits 1; WARN remains exit 0.

Phase 7 verified:
- Ran full unit suite and ruff clean.
- Ran `morphic chat` with `/status`, `/context`, and `/quit`; session `2849d812b79c` produced an 8-line append-only JSONL ledger with sequential event numbers.
- Ran `morphic context scan --json`; `.morphic/context/index.json` includes both `AGENTS.md` and `CLAUDE.md`.
- Verified `.claude/` file hashes stayed unchanged after scan.
- Fixed `morphic doctor agents --json` to suppress container initialization logs during JSON diagnostics so stdout remains machine-readable.

Phase 8 implemented:
- Added `RouteEngineRegistry`, an infrastructure adapter that converts existing `RouteToEngineUseCase` engine statuses into Chat CLI `EngineProfile` values.
- The adapter maps runtime kind, availability, context window, sandbox support, streaming support, editing support, JSON-output support, and cost profile without changing domain entities.
- `morphic chat --doctor` and the Chat REPL can now use a live route-backed registry when the app container exposes `route_to_engine`; `StaticEngineRegistry` remains the fallback.
- Unit tests use fake route statuses only; no test calls real external CLIs or LLMs.

Phase 9 implemented:
- Added `RouteChatCouncilRuntime`, an infrastructure adapter that implements `CouncilRuntimePort` and delegates planner, critic, and leader prompts to existing `RouteToEngineUseCase`.
- Route results are normalized into `CouncilTurn` cost, latency, engine id, and evidence fields; the leader output becomes the chat response through `CouncilDecision`.
- Route failure, empty output, and exceptions fall back to `LocalChatCouncilRuntime`.
- `ChatRepl` accepts an injected `CouncilRuntimePort`, and CLI wiring can create the route-backed runtime.
- Live route-backed chat council execution is guarded by `MORPHIC_CHAT_ROUTE_COUNCIL=1` so unit tests and default CLI runs do not invoke external CLIs or databases unexpectedly.

Phase 10 implemented:
- Added explicit `morphic chat --route-council` and `morphic code --route-council` flags.
- Default chat/code behavior remains local deterministic council unless the flag is present or `MORPHIC_CHAT_ROUTE_COUNCIL=1` is set.
- Unit tests monkeypatch the council runtime factory and engine registry, confirming CLI flag plumbing without invoking real route engines, external CLIs, or databases.

Phase 11 implemented:
- Added role-to-engine preferences for route-backed council execution.
- `RouteChatCouncilRuntime` now passes planner, critic, and leader preferred engines into `RouteToEngineUseCase.execute(preferred_engine=...)`.
- Added `--planner-engine`, `--critic-engine`, and `--leader-engine` to both `morphic chat` and `morphic code`.
- Unit tests use fake route calls/factories only; no test invokes real route engines, external CLIs, or databases.

Phase 12 implemented:
- Routed council role engine ids are validated before route runtime construction.
- Invalid `--planner-engine`, `--critic-engine`, or `--leader-engine` values now return a user-facing diagnostic listing valid engine ids and exit code 2.
- Invalid role engine ids are no longer hidden by the local deterministic fallback.

Phase 13 implemented:
- Added read-only `.morphic/hooks/*.json` hook validation.
- Hook diagnostics validate hook type, command, enabled flag, and secret-path risk posture without executing commands.
- Added `morphic doctor hooks` and `morphic doctor hooks --json`.
- Invalid hooks are isolated in diagnostics; FAIL exits 1 and WARN exits 0.

Phase 14 implemented:
- Added hook domain definitions and `HookRegistryPort` for validated workspace hook metadata.
- Added `hook_execution_planned` and `hook_execution_skipped` chat session events.
- Added `PlanChatHooksUseCase`, which validates hooks, records enabled hooks as planned, records disabled hooks as skipped, and refuses planning when diagnostics include FAIL results.
- Extended `WorkspaceHookRegistry` with `hooks_for()` while keeping actual hook command execution deferred.

Phase 15 implemented:
- `ExecuteChatToolUseCase` now accepts an optional `PlanChatHooksUseCase`.
- When injected, `pre_tool` hook plans are recorded before tool execution and `post_tool` hook plans are recorded after tool execution.
- Existing tool execution behavior is unchanged when no hook planner is injected.
- Session ledger ordering is preserved across hook plan, diff, tool requested/completed, verification, and post hook plan events.

Phase 16 implemented:
- Added hook execution domain contracts: `HookExecutionRequest`, `HookExecutionResult`, and `HookExecutorPort`.
- Added `hook_execution_requested` and `hook_execution_completed` chat session events.
- Added `ExecuteChatHookUseCase`, which validates hook diagnostics, skips disabled hooks without invoking the executor, executes enabled hooks through `HookExecutorPort`, and records request/completion events in the session ledger.
- FAIL hook diagnostics now block both planning and execution at the application layer.
- Shell-backed hook command execution and approval/risk policy wiring remain deferred; unit tests use a fake executor only.

Phase 17 implemented:
- Added `NoopHookExecutor`, a safe infrastructure adapter for `HookExecutorPort` that records successful hook execution results without invoking shell commands.
- `ExecuteChatToolUseCase` now accepts an optional `ExecuteChatHookUseCase` as `hook_runner`.
- When a hook runner is injected, `pre_tool` hook execution events are recorded before tool execution and `post_tool` hook execution events are recorded after tool execution.
- Existing `PlanChatHooksUseCase` injection behavior remains unchanged for planning-only paths.
- Session ledger ordering is preserved across hook execution request/completion events, diff/tool events, verification events, and post-hook execution events.
- Real shell-backed hook command execution remains deferred until explicit approval/risk policy is wired.

Phase 18 implemented:
- Added `ShellHookExecutor`, which implements `HookExecutorPort` by delegating hook commands to LAEE `LocalExecutorPort` as `shell_exec` actions.
- Hook shell execution uses the workspace root as `cwd` and includes a configurable timeout.
- LAEE `SUCCESS` observations are normalized to successful `HookExecutionResult` values; `DENIED` / `ERROR` observations become failed hook results with stderr summaries.
- `ExecuteChatToolUseCase` now stops before the tool body when an injected `pre_tool` hook runner records a failed hook result.
- Post-tool hook failure is intentionally recorded as ledger data only; no rollback behavior was added.

Phase 19 implemented:
- Added a Chat CLI hook executor factory with safe no-op default.
- `MORPHIC_CHAT_HOOK_EXECUTION=shell` explicitly opts into `ShellHookExecutor`; unset, empty, or `noop` uses `NoopHookExecutor`.
- Shell hook executor construction reuses LAEE approval mode, audit log path, and undo settings from the app container when available, with conservative local defaults otherwise.
- Unknown hook execution modes raise a validation error.
- `morphic chat --doctor --json` now reports `hook_execution_mode`.

Phase 20 implemented:
- Added `morphic hooks run <hook_type>` for explicit manual hook execution.
- Manual hook runs create a chat session ledger under `.morphic/sessions/*.jsonl` and record hook execution events.
- `morphic hooks run <hook_type> --json` emits session id, hook execution mode, diagnostics, events, results, and summary counts.
- Default manual hook execution remains no-op unless the user explicitly sets `MORPHIC_CHAT_HOOK_EXECUTION=shell`.
- Shell opt-in manual validation is covered by a test that runs `echo hook-ok` through LAEE `shell_exec` and verifies `.morphic/audit_log.jsonl`.

Phase 21 implemented:
- Added `/hooks run <hook_type>` handling inside `morphic chat`.
- REPL hook runs record both the slash command and hook execution events in the current chat session ledger.
- REPL hook execution preserves the no-op default and respects `MORPHIC_CHAT_HOOK_EXECUTION=shell`.
- Shell opt-in REPL validation is covered by a test that runs `echo repl-hook-ok` through LAEE and verifies the audit log exists.
- Deferred `D008 Hook command execution` is now complete; broader chat tool execution UX is split into a separate follow-up.

Phase 22 implemented:
- Added `NoopToolExecutor`, a safe default `ToolExecutorPort` adapter that records successful tool results without invoking local tools.
- Added `/tools run <tool_name> [json_arguments]` handling inside `morphic chat`.
- REPL tool runs record the slash command and route through `ExecuteChatToolUseCase`, producing `tool_call_requested` / `tool_call_completed` events in the current session ledger.
- Existing hook runner flow is injected around REPL tool runs, so configured `pre_tool` / `post_tool` hooks are recorded.
- Invalid JSON tool arguments return a user-facing message without crashing the REPL.
- This starts `D011 General chat tool execution UX beyond explicit hook commands`; LAEE-backed real tool execution remains a follow-up.

Phase 23 implemented:
- Added a Chat CLI tool executor factory with safe no-op default.
- `MORPHIC_CHAT_TOOL_EXECUTION=laee` explicitly opts into `LaeeToolExecutor`; unset, empty, or `noop` uses `NoopToolExecutor`.
- LAEE tool executor construction reuses the same local executor settings as shell-backed hooks.
- Unknown tool execution modes raise a validation error and surface through `morphic chat --doctor --json` with exit code 2.
- `morphic chat --doctor --json` now reports `tool_execution_mode`.
- REPL `/tools run shell_exec {"cmd":"echo tool-ok"}` is covered by an opt-in test that verifies `.morphic/audit_log.jsonl`.

Phase 24 implemented:
- `/tools run` now reports LAEE denied/error results with `success=False`, `exit_code`, and a visible `error=` summary from stderr.
- REPL tool execution now assesses risk with `RiskAssessor` from the tool name and JSON arguments before calling `ExecuteChatToolUseCase`.
- `MORPHIC_CHAT_TOOL_EXECUTION=laee` `/tools run fs_delete ...` is covered by a deny-path test that verifies the target file is preserved and `.morphic/audit_log.jsonl` records the denied action.

Phase 25 implemented:
- Added `--permission-mode` to both `morphic chat` and `morphic code`.
- Selected modes use the existing `PermissionMode` values and are persisted in session start ledger events.
- `/status` already surfaces the active permission mode, so `morphic chat --permission-mode read-only` now reports `mode=read-only`.
- Read-only mutating `/tools run` attempts now return a user-facing `permission denied: ...` assistant message instead of crashing the REPL.

Key design decisions:
- Start with a line-oriented `morphic chat` REPL; defer full-screen Textual UI until the event/session model is stable.
- `.morphic/` becomes the canonical workspace metadata layer over time.
- `.claude/`, `AGENTS.md`, `GEMINI.md`, Codex metadata are discovery/import sources first, export/projection targets later.
- Roles and engines are distinct: planner/critic/leader are council responsibilities; Claude/Gemini/Codex/OpenHands/Ollama are runtime backends.
- Morphic owns session ledger, approval policy, tool normalization, context index, memory writes, and final decisions.
- Existing `specs/council-pilot/` remains the lower-level two-engine debate spike; `morphic-chat-cli` is the higher-level terminal UX and harness.

Recommended next implementation step:
- Next recommended slice: add explicit invalid permission mode diagnostics tests and help text coverage for the new CLI option.

> Last updated: 2026-05-20
> Last commit: `feat(router): Goal Classifier Router for planner model selection (TD-195)`
> Branch: `feature/goal-classifier-router` (HEAD `e49499c`)

---

## What Was Just Done (2026-05-20)

### Sprint 91 (TD-195) — Goal Classifier Router

**TD-195: Per-goal routing of `LLMPlanner` between Sonnet 4.6 and Haiku 4.5**

Spec-driven (`specs/goal-classifier-router/{spec,plan,tasks.md}`), full
TDD on `feature/goal-classifier-router`. Implements:

- `GoalClassifierPort` (domain ABC) + `GoalClassification` VO + AD-3
  6-bucket `ReasonCategory` Literal.
- `PlannerModelRouter.select_for(goal) → (PlannerModel, GoalClassification | None)`
  — confidence-gated, fail-safe to Sonnet on timeout / parse error.
- `LLMGoalClassifier` (Haiku 4.5 via LiteLLM) + `LocalGoalClassifier`
  (qwen3:8b via Ollama) — share byte-identical `SYSTEM_PROMPT` per TD-190.
- `EventBusPort` + `InMemoryEventBus` + `RouterObservingEventBus`
  decorator (metrics + structured logs). `sha256(goal)[:16]` only —
  raw goal **never** serialized.
- `MORPHIC_PLANNER_ROUTER` env flag (default `disabled`, opt-in
  `enabled` — adapter is auto-selected at DI wire time: remote Haiku 4.5
  when `ANTHROPIC_API_KEY` is set, else local qwen3:8b).

**Live A/B verdict** (3 arms × 10 goals × 3 trials, $0.97 total):

- entity_preserved: 83.8% (Sonnet) → 81.3% (Router) = **−2.5pt** (≤5pt ✓)
- plan_eval:        0.898 → 0.884 = **−0.014** (≤0.030 ✓)
- avg cost / call:  $0.01351 → $0.01218 = **−9.85%**
- Routing: 4/10 Haiku, 6/10 Sonnet (entity-stressed benchmark)
- Captured-saving: 20.9% (paper bar 30% missed — workload-mix structural)

Memo: `memory/planner_router_ab_2026_05_20.md`. Ship recommendation
documented.

### Sprint 90 (TD-194) — Council Pilot full merge
(See `docs/CHANGELOG.md` for the v0.6.1 → v0.6.2 detail.)

---

## Current State Summary

### Progress

```
Phase  1-7:  Foundation → UCL          ██████████ 100%
Phase 8-12:  Intelligence + Two Worlds ██████████ 100%
Phase 13:    Multi-Agent Collaboration ██████████ 100%  (6/6 sprints)
Sprint 14.x: Cost/CLI/Artifact/o4-mini ██████████ 100%  (TD-092 to TD-098)
Sprint 15.x: Fractal Engine (7 sprints)██████████ 100%  (TD-099 to TD-106)
Sprint 16.x: E2E + Learning PG        ██████████ 100%  (TD-107 to TD-110)
Sprint 17.x: PG永続化 + N-gram        ██████████ 100%  (TD-111, TD-112)
Sprint 18.x: MCP + A2A Protocol (5sp) ██████████ 100%  (TD-113 to TD-118)
Phase 14:    A2A Protocol              ██████████ 100%  (5/5 sprints)
Sprint 19-20: CLI/Evolution/Marketplace██████████ 100%  (TD-119 to TD-123)
Sprint 21-22: Quality/Dedup/Skip       ██████████ 100%  (TD-124 to TD-127)
Sprint 23-24: BUG fix/OpenHands/SQLite ██████████ 100%  (TD-128 to TD-131)
Sprint 25.x: CLI + API (5 sprints)     ██████████ 100%  (TD-132 to TD-136)
Sprint 26.1: Pytest warnings fix       ██████████ 100%  (TD-137)
Sprint 27.1: Frontend UI Expansion     ██████████ 100%  (TD-138)
Sprint 27.2: Memory + A2A Pages        ██████████ 100%  (TD-139)
Sprint 27.3: Dashboard + Plans List    ██████████ 100%  (TD-140)
Sprint 28.1: Chrome Extension          ██████████ 100%  (TD-141)
Sprint 28.2: OpenHands Driver Update   ██████████ 100%  (TD-142)
Sprint 28.3: Production Hardening      ██████████ 100%  (TD-143)
Sprint 29.1: README/LICENSE/Version    ██████████ 100%  (TD-144)
Sprint 29.2: CI/CD Pipeline           ██████████ 100%  (TD-145)
Sprint 29.3: Settings API + Page       ██████████ 100%  (TD-146)
Sprint 29.4: Route Test Coverage       ██████████ 100%  (TD-147)
Sprint 29.5: Env Validation Script     ██████████ 100%  (TD-148)
Sprint 30.1: PG pgvector Auto-Init     ██████████ 100%  (TD-149)
Sprint 31.1: Chrome Extension README   ██████████ 100%  (TD-150)
Sprint 31.2: TaskGraph Enhancement     ██████████ 100%  (TD-151)
Sprint 31.3: Codex CLI E2E Routing     ██████████ 100%  (TD-152)
Sprint 31.4: OpenHands Sandbox E2E     ██████████ 100%  (TD-153)
Sprint 31.5: Version Bump → v0.5.1     ██████████ 100%  (TD-154)
Sprint 32.1: Auto-route Intelligence   ██████████ 100%  (TD-155)
Sprint 33.1: Parallel Decomp + QualGate██████████ 100%  (TD-159)
Sprint 33.2: Lucide React UI Overhaul  ██████████ 100%  (TD-160)
Sprint 33.3: SSE Streaming + Timeline  ██████████ 100%  (TD-161)
Sprint 34.1: TaskGraph Live Animations ██████████ 100%  (TD-162)
Sprint 35:   Living Fractal Reflection ██████████ 100%  (TD-163)
Sprint 35.1: SSE Fix + Auto-Navigate   ██████████ 100%  (TD-164)
Sprint 35.2: Reflection Badge 4-Layer ██████████ 100%  (TD-165)
Sprint 35.3: Fractal Status + Complexity██████████ 100%  (TD-166)
Sprint 36:   SIMPLE Bypass + Intent    ██████████ 100%  (TD-167)
Sprint 36.1: Gate 2 Skip Terminal      ██████████ 100%  (TD-168)
Sprint 37:   Parallel Node Execution   ██████████ 100%  (TD-169)
Sprint 37.1: UI Auto-Refresh           ██████████ 100%  (TD-170)
Sprint 37.2: Reflection Skip           ██████████ 100%  (TD-171)
Sprint 38:   Live E2E Round 18         ██████████ 100%  (TD-172)
Sprint 38.1: Planner Candidate Cache   ██████████ 100%  (TD-173)
Sprint 38.2: Fractal Visibility + Final██████████ 100%  (TD-174)
Sprint 39.1: Fractal Concurrency Throttle██████████ 100%  (TD-175)
Sprint 39.2: Goal Grounding + Output-Aware Eval + Skill Loop + Artifacts ██████████ 100%  (TD-176 to TD-179)
Sprint 39.3: Zombie Task Prevention  ██████████ 100%  (TD-180)
Sprint 39.4: Hard Timeout + Round 19 ██████████ 100%  (TD-181)
─────────────────────────────────────────────────
Overall: 100% | 84 sprints | TD-001 to TD-180 | v0.5.1
```

### Test Count
- **3,110 unit tests**, 148 integration, **0 failures**, **0 warnings**, lint clean
- TD-001 to TD-180 recorded in `docs/TECH_DECISIONS.md`

### Engine Routing Status
| Engine | Status | Live Verified |
|--------|--------|---------------|
| Gemini CLI (v0.34.0) | ✅ Working | Round 7-9 ($0.031/query) |
| Claude Code CLI (v2.1.80) | ✅ Working | Round 4-8 ($0.085/query) |
| o4-mini via LiteLLM API | ✅ Working | Round 9 ($0.001/query) |
| Ollama (v0.18.0, qwen3:8b) | ✅ Working | Round 1-9 ($0.00) |
| Codex CLI (v0.116.0) | ✅ Working | Round 15 (42.6s, E2E via engine routing) |
| OpenHands (v0.59.0, Gemini) | ✅ Working | Round 16 (sandbox E2E, file create + exec) |

### API Key Status
| Provider | Status |
|----------|--------|
| Claude (claude-sonnet-4-6) | ✅ Working |
| Gemini (gemini-3-pro-preview, gemini-2.5-flash) | ✅ Working |
| OpenAI (o4-mini) | ✅ Working ($50 funded) |
| Ollama (qwen3:8b) | ✅ Working (local, $0) |

### Live E2E Verification History (16 Rounds)

| Round | Date | What was verified | Cost |
|-------|------|-------------------|------|
| 1-3 | 2026-03-20 | Basic execution, ReAct bypass, Discussion Phase | $0.072 |
| 4-6 | 2026-03-21-23 | Engine routing, CLAUDE.md contamination fix, Gemini prefix fix | — |
| 7 | 2026-03-23 | Full adaptive discussion: Gemini + Claude + Discussion R3 | $0.133 |
| 8 | 2026-03-23 | Artifact chaining E2E: Gemini→Claude sequential, deps inferred | $0.116 |
| 9 | 2026-03-23 | o4-mini + 3-engine: Gemini→o4-mini→Ollama all in single task | $0.033 |
| 10 | 2026-03-26 | Fractal Engine E2E: Planner→Gate①→Execute→Gate②→Learning | $0.00 |
| 11 | 2026-03-26 | Learning closed-loop: Task A→ErrorPatterns→Task B→injected | $0.00 |
| 12 | 2026-03-27 | MCP Live: mcp-server-fetch real connection, ReactExecutor routing | $0.00 |
| 13 | 2026-03-27 | Marketplace Live: MCP Registry v0.1 search + safety scoring | $0.00 |
| 14 | 2026-04-02 | OpenHands: Docker socket, sandbox build, agent loop started | $0.00 |
| 15 | 2026-04-02 | Codex CLI E2E: engine routing → codex exec → autonomous code gen (42.6s) | $0.00 |
| 16 | 2026-04-02 | OpenHands Sandbox: create→exec→finish, Gemini 2.5 Flash, Docker sandbox | ~$0.01 |
| 17 | 2026-04-05 | Fractal Engine E2E: "2+2" → plan→3 subtasks→execute→reflection satisfied | $0.00 |
| 18 | 2026-04-05 | Perf validation: 2 SIMPLE tasks, bypass+gate2+reflection skip, <5-10s | $0.00 |

---

## Next Optimization Candidates

| ID | Candidate | Description | Status |
|----|-----------|-------------|--------|
| ~~C~~ | ~~Planner/Evaluator並列~~ | Data dependency: evaluator needs plan output | **Infeasible** |
| ~~D~~ | ~~UI自動リフレッシュ~~ | 3s polling via useAutoRefresh (TD-170) | **Done** |
| ~~E~~ | ~~ノード並列実行~~ | `asyncio.gather`で同時実行 (TD-169) | **Done** |
| ~~F~~ | ~~Live E2E Round 18~~ | TD-167+168+169+171を実測検証 (TD-172) | **Done** |
| ~~G~~ | ~~Planner candidate caching~~ | 同じgoalのplanner結果をキャッシュ (TD-173) | **Done** |
| ~~H~~ | ~~Reflection skip for simple plans~~ | 1ノード成功はreflection不要 (TD-171) | **Done** |

---

## What Was Just Done

### Sprint 39.4 (TD-181) — Hard Timeout + Round 19 E2E

**TD-181**: **asyncio.wait_for Hard Timeout + Live E2E Round 19**

**Round 19 result: FAIL (1/7)** — three layered issues discovered:

1. **No wall-clock timeout** (fixed): `_execute_plan` had no time limit. Added
   `asyncio.wait_for(timeout=180s)` as hard cancellation. Cooperative `_is_timed_out()`
   checks in retry/reflection loops. All remaining RUNNING subtasks marked FAILED.

2. **Bypass over-classification** (identified): "スライドにして" classified as SIMPLE
   by bypass classifier, returning text-only answer. Needs output-requirement
   awareness in bypass decision.

3. **No agent engine delegation** (architectural): Content creation (slides, infographics)
   should route to Claude Code / Gemini CLI — not local LAEE + qwen3:8b. User feedback:
   "python-pptxとか直接入れちゃうのは特化 — フラクタルの設計思想と異なる".

- **4 new tests** (3114 total, 0 fail)
- **Key config**: `fractal_max_execution_seconds=180` (settings.py)

### Sprint 39.3 (TD-180) — Zombie Task Prevention

**TD-180**: **Repetitive Tool Loop Detection + Max-Iterations FAILED + Catch-All**

**Incident**: Task "氷川神社の歴史を調べ、スライドにして" ran 14+ hours in "running" status.
Audit log showed: 10x `web_search(query="検索キーワード")` (old bug), fake PPTX write,
then 170x `system_notify` loop. Three design defects identified and fixed:

1. **Repetitive loop detection**: ReactExecutor now tracks tool+args signature.
   Same call 3x in a row → `terminated_reason="repetitive_tool_loop"` → immediate stop.
2. **max_iterations → FAILED**: LangGraphTaskEngine now checks `terminated_reason`.
   `"max_iterations"` or `"repetitive_tool_loop"` → subtask marked `FAILED` (was unconditional `SUCCESS`).
3. **Catch-all exception handler**: `_execute_node_safe` now catches all `Exception` types,
   marks node `FAILED` with error message. Prevents nodes stuck in `RUNNING` from unexpected errors.

- **8 new tests**: 3 loop detection + 5 status guarantees
- **3 existing tests updated**: Use varying args to avoid false-positive loop detection

### Sprint 39.2 (TD-176 to TD-179) — Goal Grounding + Output-Aware Eval + Skill Loop + Artifacts

**TD-176**: Goal Grounding — entity preservation in planner/executor prompts
**TD-177**: Output-Aware Evaluation — OutputRequirement VO + LLM classifier + Gate② hints
**TD-178**: Skill Acquisition Loop — discover→safety filter→install→retry (max 1)
**TD-179**: Artifact Pipeline — audit log file tracking + TaskEntity.artifact_paths + API

### Sprint 36 (TD-167) — SIMPLE Task Fractal Bypass

**TD-167**: **SIMPLE Task Fractal Bypass with LLM Intent Analysis**
- **Pure LLM intent analysis**: All classification goes through LLM for nuanced semantic understanding (~15-30s). No rule-based shortcuts — the model decides.
- **Bypass path**: SIMPLE goals skip fractal planning entirely → single SubTask with SIMPLE complexity → inner engine (LangGraph) direct-LLM fast path.
- **Conservative design**: LLM failure or uncertain classification → defaults to fractal planning (never false-positive bypass).
- **Performance**: SIMPLE tasks ~4.5min → ~45-60s (4-6x faster). MEDIUM/COMPLEX tasks: +15-30s overhead for classification.
- **New file**: `infrastructure/fractal/bypass_classifier.py` (FractalBypassClassifier)
- **18 new tests**: LLM classification (13), engine integration (5)

### Sprint 38.2 (TD-174) — Fractal Child Node Visibility + Final Answer

**TD-174**: **Expose Fractal Child Nodes in UI + Final Answer Display**
- **Child node visibility**: `_execute_expandable` now adds child nodes to `task.subtasks` + emits `node_spawned` SSE with `parent_id`
- **React Flow dynamic growth**: child nodes appear with dependency edges to parent
- **Final Answer**: `final_answer` field added to TaskEntity, DB, API — prominent green-bordered UI section
- **progress_pct**: computed server-side in TaskResponse

### Sprint 38.1 (TD-173) — Planner Candidate Caching

**TD-173**: **Cache Planner Candidates for Repeat Goals**
- **Opt-in flag**: `cache_planner_candidates` constructor param (default False, True in production)
- **Cache key**: `goal::nesting_level` — deep-copied on store/retrieve
- **Savings**: ~15-30s per repeat goal (one LLM call eliminated)
- **4 new tests** in `TestPlannerCache` class

### Sprint 38 (TD-172) — Live E2E Round 18

**TD-172**: **Performance Optimization Validation**
- 2 SIMPLE tasks verified: "What is 2+2?" and "List three advantages of Python..."
- All 3 applicable optimizations fired: TD-167 bypass, TD-168 gate2 skip, TD-171 reflection skip
- End-to-end latency: <5-10s (previously ~4.5 minutes)
- Total cost: $0.00 (Ollama local)

### Sprint 37.2 (TD-171) — Reflection Skip for Single-Node Success

**TD-171**: **Skip Reflection for Single-Node Successful Plans**
- **Opt-in flag**: `skip_reflection_for_single_success` constructor param (default False, True in production)
- **Skip condition**: 1 completed node + SUCCESS + first reflection round → return `[]` immediately
- **Savings**: ~30s per single-node plan (one LLM call eliminated)
- **3 new tests** in `TestReflectionSkip` class

### Sprint 37.1 (TD-170) — UI Auto-Refresh

**TD-170**: **Dashboard/Cost/Engines Auto-Refresh**
- **useAutoRefresh hook**: Shared 3s polling hook, active when tasks running/pending
- **3 pages updated**: Dashboard, Cost, Engines — all now auto-refresh during task execution
- **Next.js build passes**: 16 pages generated successfully

### Sprint 37 (TD-169) — Parallel Node Execution

**TD-169**: **Parallel Node Execution via asyncio.gather**
- **Opt-in flag**: `parallel_node_execution` constructor param (default False, True in production)
- **Batch execution**: All pending nodes drain into a batch, execute via `asyncio.gather`
- **Sequential fallback**: Artifact chaining, budget tracking, fallback ordering preserved when disabled
- **Performance**: 3-node plan ~90s → ~30s (3x speedup)
- **4 new tests**: parallel multi-node, single with parallel, mixed success/failure, sequential order

### Sprint 36.1 (TD-168) — Gate 2 Skip for Successful Terminal Nodes

**TD-168**: **Gate 2 Skip Optimization**
- **Opt-in flag**: `skip_gate2_for_terminal_success` constructor param (default False, True in production)
- **Skip condition**: Terminal node + SUCCESS status + non-empty result → skip Gate 2 LLM call
- **Still evaluates**: Failed nodes, empty results, non-terminal nodes
- **Performance**: ~30s saved per successful terminal node (90s for typical 3-node plan)
- **4 new tests**: skip on success, no skip on failure/empty/non-terminal

### Previous: Sprint 35.3 (TD-166)

- **Bug fixes**: Subtask status persistence + ReAct infinite loop prevention
- **Live E2E Round 17**: "What is 2+2?" → plan→3 subtasks→reflection satisfied (~4.5 min, $0.00)
- **Live E2E Round 18**: 2 SIMPLE tasks → bypass+gate2 skip+reflection skip (<5-10s, $0.00)

### Previous: Sprint 35-35.2 (TD-163 to TD-165)

1. **TD-163**: Living Fractal — Reflection-driven dynamic node spawning. Queue-based execution, 3 SSE event types.
2. **TD-164**: SSE inactivity timeout fix + dashboard auto-navigate.
3. **TD-165**: Reflection badge 4-layer vertical slice (Domain→Infra→API→UI).

### Previous: Sprint 31.1-31.3 (TD-150 to TD-152)

1. **TD-150**: Chrome Extension README — installation + usage docs added
2. **TD-151**: TaskGraph.tsx enhanced — click-to-select detail panel, cost/engine badges, glow highlight
3. **TD-152**: **Codex CLI E2E (Live Round 15)** — `POST /api/engines/run` with `engine: codex_cli` → Codex autonomously explored codebase, wrote code, 42.6s, 142K tokens (107K cached), no fallback needed
4. **TD-153**: **OpenHands Sandbox E2E (Live Round 16)** — Docker container → Gemini 2.5 Flash → CodeActAgent → file create + python exec → finish. Claude model rejected (temp+top_p bug in OH v0.59)
5. **TD-154**: **Version Bump v0.5.1** — 7 files updated (pyproject.toml, main.py, settings.py, serve.py, CLAUDE.md, 2 test files)

### Previous: Sprint 30.1: PostgreSQL pgvector Auto-Init (TD-149)

- Docker disk space exhaustion caused PG crash loop → `docker system prune` freed 6.7GB
- Fresh volume lacked `CREATE EXTENSION vector` → memories table failed on `VECTOR(384)`
- Added `scripts/init_pg.sql` mounted to `/docker-entrypoint-initdb.d/` in `docker-compose.yml`
- `USE_POSTGRES=true` now works out of the box on fresh installs

### Previous: Sprint 29.1-29.5 (TD-144 to TD-148)

1. **TD-144**: README.md, LICENSE (MIT), Makefile, version alignment 0.4.0→0.5.0-alpha
2. **TD-145**: GitHub Actions CI pipeline — lint, unit tests, UI build, Docker build
3. **TD-146**: Settings API + frontend Settings page
4. **TD-147**: Route unit tests for cost, memory, models (23 tests)
5. **TD-148**: `.env` validation script

### Previous: Sprint 28.1-28.3 (TD-141 to TD-143)

### Previous: Sprint 25.1-25.5 (TD-132 to TD-136)

| Sprint | TD | What | Key Commands |
|--------|-----|------|-------------|
| 25.1 | TD-132 | Memory Layer CLI (5 subcmds) | `morphic memory list/search/show/stats/delete` |
| 25.2 | TD-133 | Fallback Inspection CLI (3 subcmds) | `morphic fallback history/failures/stats` |
| 25.3 | TD-134 | Learning Repository CLI (3 subcmds) | `morphic learning list/search/stats` |
| 25.4 | TD-135 | Context Export CLI (3 subcmds) | `morphic context export/export-all/platforms` |
| 25.5 | TD-136 | Conflict Resolver API | `POST /api/cognitive/conflicts` |

---

## Sprint History (Condensed)

> Full details: `docs/TECH_DECISIONS.md` (TD-001 to TD-174)

| Phase | Sprints | Key Deliverables |
|-------|---------|-----------------|
| 14.x | 5 sprints | Cost+CLI+Config, CLI Hardening, Gemini Fix, Artifact Dep, o4-mini |
| 15.x | 8 sprints | Fractal Engine: Domain→Planner→Gate①②→Core→Wiring→Learning |
| 16.x | 3 sprints | Fractal E2E (Round 10), Learning PG永続化, Planner統合 |
| 17.x | 2 sprints | InMemory→PG全8リポジトリ, N-gram learning match |
| 18.x | 6 sprints | MCP hardening, A2A Protocol (domain→infra→usecase→API→integration) |
| 19-20 | 5 sprints | MCP Live E2E, A2A CLI, Evolution tests, Marketplace Live, Prompt Templates |
| 21-22 | 4 sprints | Competitive Analysis, PG warnings fix, Token dedup, E2E skip markers |
| 23-24 | 4 sprints | BUG-002/003+serve+doctor, OpenHands scaffold, SQLite fallback, CLI gap-fill |
| 25.x | 5 sprints | Memory CLI, Fallback CLI, Learning CLI, Context Export CLI, Conflict API |
| 26.1 | 1 sprint | Pytest warnings elimination (316 deprecated + 3 runtime) |
| 27.1 | 1 sprint | Frontend UI: Engines + Cost + Tasks pages, nav update |
| 27.2 | 1 sprint | Frontend UI: Memory + A2A pages, API client expansion |
| 27.3 | 1 sprint | Dashboard redesign + Plans list page |
| 28.1 | 1 sprint | Chrome Extension (Manifest v3, Context Bridge) |
| 28.2 | 1 sprint | OpenHands driver API update + E2E verification |
| 28.3 | 1 sprint | Production hardening (Docker, compose, nginx) |
| 29.1 | 1 sprint | README, LICENSE, Makefile, version alignment |
| 29.2 | 1 sprint | GitHub Actions CI pipeline (4 jobs) |
| 29.3 | 1 sprint | Settings API + frontend Settings page |
| 29.4 | 1 sprint | Route unit tests (cost, memory, models) |
| 29.5 | 1 sprint | .env validation script |
| 30.1 | 1 sprint | PostgreSQL pgvector auto-init |
| 31.1 | 1 sprint | Chrome Extension README documentation |
| 31.2 | 1 sprint | TaskGraph visualizer enhancement (detail panel + badges) |
| 31.3 | 1 sprint | Codex CLI E2E routing (Live Round 15) |
| 31.4 | 1 sprint | OpenHands Sandbox E2E (Live Round 16) |
| 31.5 | 1 sprint | Version bump 0.5.0-alpha → 0.5.1, git tag |
| 32.1 | 1 sprint | Auto-route intelligence (TD-155) |
| 33.1 | 1 sprint | Parallel decompose + quality gate (TD-159) |
| 33.2 | 1 sprint | Lucide React UI overhaul (TD-160) |
| 33.3 | 1 sprint | SSE streaming + timeline (TD-161) |
| 34.1 | 1 sprint | TaskGraph live animations (TD-162) |
| 35   | 1 sprint | Living Fractal reflection (TD-163) |
| 35.1 | 1 sprint | SSE fix + auto-navigate (TD-164) |
| 35.2 | 1 sprint | Reflection badge 4-layer (TD-165) |
| 35.3 | 1 sprint | Fractal status + complexity (TD-166) |
| 36   | 1 sprint | SIMPLE bypass + LLM intent (TD-167) |
| 36.1 | 1 sprint | Gate 2 skip for terminal success (TD-168) |
| 37   | 1 sprint | Parallel node execution via asyncio.gather (TD-169) |
| 37.1 | 1 sprint | UI auto-refresh: Dashboard, Cost, Engines (TD-170) |
| 37.2 | 1 sprint | Reflection skip for single-node success (TD-171) |
| 38   | 1 sprint | Live E2E Round 18: perf optimization validation (TD-172) |
| 38.1 | 1 sprint | Planner candidate caching for repeat goals (TD-173) |
| 38.2 | 1 sprint | Fractal child node visibility + final answer (TD-174) |

---

## Implementation Completeness (2026-04-02)

### Codebase Scale
- **~420+ Python source files** across 4 Clean Architecture layers
- **3,020 unit + 148 integration = 3,168 total**, 0 failures, 0 warnings, lint clean
- **TD-001 to TD-167** recorded in TECH_DECISIONS.md
- **17 rounds** of live E2E verification ($0.40 total), **all 6 engines verified**
- **18 frontend pages** + Chrome Extension, 0 TypeScript errors

### Overall Progress
```
Code implementation:     ████████████████████ 100%
Test coverage:           ████████████████████ 100%  (3,150 total, 0 warnings)
CLI completeness:        ████████████████████ 100%  (17 command groups)
API completeness:        ████████████████████ 100%  (12 route modules)
Live E2E verification:   ████████████████████ 100%  (6/6 engines, 17 rounds, all sandbox tested)
Production readiness:    ████████████████████ 100%  (Docker+compose+nginx+CI/CD+PG auto-init)
Frontend UI:             ████████████████████ 100%  (18 pages + Extension)
```

---

## Key Architecture Decisions
- Engine drivers = autonomous agent runtimes (NOT just LLM API wrappers)
- Execution priority: Engine routing → ReactExecutor → Direct LLM
- Artifact flow = LLM-specified or inferred linear chain + dependency inference
- LOCAL_FIRST: Ollama ($0) whenever possible
- Never specialize for test scenarios — generic framework only
- Gate ① cost strategy: Ollama first ($0), cloud models optional

### Execution Pipeline
```
POST /api/tasks
  → IntentAnalyzer → ModelPreferenceExtractor → CollaborationMode
    → _apply_artifact_flow() [artifact schemas + dependency inference]
    → ArtifactDependencyResolver.resolve() [on plan approval]
  → LangGraphTaskEngine._execute_batch()
    → Each subtask:
      1. _inject_artifacts() — pull from completed dependencies
      2. Engine routing (Gemini CLI / Claude Code / Codex CLI / Ollama)
      3. ReactExecutor fallback — tool-augmented LLM (o4-mini, etc.)
      4. Direct LLM fallback — text completion
      5. _extract_output_artifacts() — smart parsing
  → _run_discussion() [if multi-model]
  → Validation → InsightExtractor → ExecutionRecord → Learning
```

### Conflict Detection
```
POST /api/cognitive/conflicts
  → Fetch L1-L3 memories → Convert to ExtractedInsight
  → ConflictResolver.detect_conflicts() [Jaccard + Negation, O(n²)]
  → Optional: resolve_all() [higher confidence wins]
  → ConflictListResponse
```

---

## Key Files
| File | Purpose |
|------|---------|
| `CLAUDE.md` | Project constitution (~95KB, v0.5.0-alpha) |
| `docs/TECH_DECISIONS.md` | 154 ADRs (TD-001 to TD-154) |
| `docs/CONTINUATION.md` | This file — handoff state |
| `shared/config.py` | All settings (pydantic-settings) |
| `interface/api/container.py` | DI wiring (PG/SQLite/InMemory) |
| `infrastructure/fractal/fractal_engine.py` | FractalTaskEngine — recursive engine core |
| `infrastructure/task_graph/engine.py` | Core execution pipeline + discussion |
| `interface/api/routes/` | 12 route modules (tasks, plans, cost, memory, a2a, cognitive, settings, etc.) |
| `interface/cli/commands/` | 17 CLI command groups |

## Dev Commands
```bash
uv run --extra dev pytest tests/unit/ -v          # 2,943 unit tests
uv run --extra dev pytest tests/integration/ -v   # 148 integration tests
uv run --extra dev ruff check .                    # lint
uv run uvicorn interface.api.main:app --host 0.0.0.0 --port 8001 --reload  # server
```

## Remaining Sprint Plan (v0.5.0 → v0.5.1)

### Sprint 31.1: Chrome Extension Polish (TD-150) — ✅ DONE
- [x] README extension section with installation + usage instructions

### Sprint 31.2: Task Graph Visualizer Enhancement (TD-151) — ✅ DONE
- [x] SubTaskPanel slide-out detail panel (status, cost, model, engine, code, output, error)
- [x] Click-to-select with glow highlight, onPaneClick to deselect
- [x] Cost badge + engine label on each node
- [x] Edge styling: strokeWidth 2 for success, animated pulse for running

### Sprint 31.3: Codex CLI Engine Routing E2E (TD-152) — ✅ DONE
- [x] `POST /api/engines/run` with `engine: codex_cli` → success (42.6s)
- [x] Codex CLI autonomously explored codebase, wrote code, created files
- [x] Recorded as Live E2E Round 15

### Sprint 31.4: OpenHands Sandbox E2E (TD-153) — ✅ DONE
- [x] Started OpenHands on port 3001 with Docker socket mount
- [x] Configured Gemini 2.5 Flash (Claude rejected due to temp+top_p bug in OH v0.59)
- [x] CodeActAgent: file create → cat → python3 exec → finish with correct output
- [x] Recorded as Live E2E Round 16

### Sprint 31.5: Final Polish (TD-154) — ✅ DONE
- [x] Bumped version 0.5.0-alpha → 0.5.1 across 7 files
- [x] Updated CONTINUATION.md with final assessment
- [x] Git tag `v0.5.1`

### Sprint 34.1–34.2: TaskGraph Live Animations + SSE Live Verification (TD-162) — ✅ DONE
- [x] 4 CSS keyframe animations: node-enter, node-pulse, status-flash, edge-flow
- [x] React state tracking (prevNodeIds/prevStatusMap refs) for differential rendering
- [x] Stagger delay (80ms per node) for cascade effect on batch appearance
- [x] Goal node enter animation via ReactFlow className prop
- [x] Edge CSS transitions for smooth status color changes
- [x] SSE live verification: POST task → stream events → confirmed snapshot/subtask_completed/task_completed flow
- [x] 2,978 unit tests passed, lint clean, build OK

## Progress Assessment (2026-04-02)

### Summary: Total 100% — v0.5.1 Released

| Area | Progress | Detail |
|------|----------|--------|
| **Backend** | 100% | Domain 15 entities, 23 ports, 18 services / Application 17 use cases / Infrastructure 6 drivers, full stack |
| **Tests** | 100% | 2,943 unit + 148 integration = 3,091 total, 0 failures, 0 warnings, lint clean |
| **CLI** | 100% | 17 command groups (task/plan/model/cost/mcp/engine/fallback/learning/marketplace/memory/context/evolution/cognitive/benchmark/a2a/doctor/serve) |
| **API** | 100% | 13 route modules (tasks/plans/cost/models/engines/marketplace/evolution/cognitive/benchmarks/memory/a2a/settings) |
| **Frontend** | 100% | 18 pages + Chrome Extension, 0 TypeScript errors |
| **Live E2E** | 100% | 16 rounds, 6/6 engines E2E verified. All sandbox tested |
| **Production** | 100% | Docker+compose+nginx+CI/CD+PG auto-init, PG+SQLite+InMemory, README+LICENSE+Makefile |

### USER ACTION REQUIRED
- ~~**Codex CLI**: `codex login`~~ → ✅ Done (2026-04-02, Live E2E Round 15)
- ~~**OpenHands sandbox**~~ → ✅ Done (2026-04-02, Live E2E Round 16, Gemini 2.5 Flash)

---

## Absolute Constraints
- Reasoning: English | Response: Japanese
- File changes → concise English commit message at end
- Workflow: 1 fix → commit & push → report
- Never specialize for test scenarios — generic framework only
- Engine drivers are autonomous agent runtimes that write and execute code
