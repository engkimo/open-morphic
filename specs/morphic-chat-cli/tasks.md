# Tasks - Morphic Chat CLI

> **Spec:** [`spec.md`](spec.md)
> **Plan:** [`plan.md`](plan.md)
> **Status:** draft

## Phase 0 - Design Lock

- [ ] T001 Confirm MVP command names: `morphic chat`, `morphic code`, `morphic context scan`.
- [ ] T002 Confirm whether the first UI is line-oriented REPL or Textual. Recommended: line-oriented REPL.
- [ ] T003 Confirm `.morphic/` layout and no-overwrite rule for existing `.claude/`, `AGENTS.md`, `GEMINI.md`.
- [ ] T004 Confirm MVP roles: planner, critic, leader.
- [ ] T005 Confirm permission modes and default. Recommended: `confirm-destructive`.

## Phase 1 - Domain and Ports

- [x] T101 Add `domain/entities/chat_event.py` with append-only session event models.
- [x] T102 Add `domain/entities/chat_session.py` with session id, status, goal, permission mode, and event sequence.
- [x] T103 Add `domain/entities/workspace_context.py` with context source and context index models.
- [x] T104 Add `domain/entities/approval.py` with approval request/decision models.
- [x] T105 Add `domain/ports/chat_session_store.py`.
- [x] T106 Add `domain/ports/context_discovery.py`.
- [x] T107 Add `domain/ports/council_runtime.py`.
- [x] T108 Add `domain/ports/tool_executor.py` or reuse an existing LAEE-compatible port if present.
- [x] T109 Add import-boundary tests for new domain files.
- [x] T110 Add `domain/ports/engine_registry.py` skeleton for chat engine profiles.

## Phase 2 - Application Use Cases

- [x] T201 Add `StartChatSessionUseCase`.
- [x] T202 Add `ResumeChatSessionUseCase`.
- [x] T203 Add `SendChatMessageUseCase`.
- [x] T204 Add `ExecuteSlashCommandUseCase`.
- [x] T205 Add `DiscoverWorkspaceContextUseCase`.
- [x] T206 Add `RequestToolApprovalUseCase`.
- [x] T207 Add `SummarizeChatSessionUseCase`.
- [x] T208 Unit test event sequencing and append-only behavior.
- [x] T209 Unit test slash command handling.
- [x] T210 Unit test read-only permission behavior.

## Phase 3 - Infrastructure

- [x] T301 Add `infrastructure/chat/jsonl_session_store.py`.
- [x] T302 Add `infrastructure/context/workspace_context_discovery.py`.
- [x] T303 Add context discovery support for root `AGENTS.md`.
- [x] T304 Add context discovery support for `CLAUDE.md`.
- [x] T305 Add context discovery support for `.claude/agents`, `.claude/skills`, `.claude/commands`, `.claude/rules`.
- [x] T306 Add context discovery support for `GEMINI.md`.
- [x] T307 Add context discovery support for `.morphic/context`.
- [x] T308 Write `.morphic/context/index.json` without editing source files.
- [x] T309 Add fake/local council runtime adapter for MVP.
- [x] T310 Add engine registry skeleton.

## Phase 4 - CLI Interface

- [x] T401 Add `interface/cli/chat_command.py`.
- [x] T402 Add line-oriented `ChatRepl`.
- [x] T403 Add slash command parser.
- [x] T404 Implement `/help`.
- [x] T405 Implement `/status`.
- [x] T406 Implement `/context`.
- [x] T407 Implement `/engines`.
- [x] T408 Implement `/diff`.
- [x] T409 Implement `/quit`.
- [x] T410 Wire `morphic chat`.
- [x] T411 Wire `morphic chat --resume latest`.
- [x] T412 Wire `morphic code "<goal>"`.

## Phase 5 - Approval and Execution Harness

- [x] T501 Add approval prompt rendering.
- [x] T502 Block edits in `read-only` mode.
- [x] T503 Route mutation through LAEE-compatible executor.
- [x] T504 Record `approval_requested` and `approval_resolved` events.
- [x] T505 Record `tool_call_requested` and `tool_call_completed` events.
- [x] T506 Add diff proposal event before edits.
- [x] T507 Add verification command event for tests/lint.

## Phase 6 - Diagnostics and Automation

- [x] T601 Add `morphic context scan`.
- [x] T602 Add `morphic doctor agents`.
- [x] T603 Add JSON output for context scan.
- [x] T604 Add JSON output for doctor.
- [x] T605 Add stable exit codes for non-interactive commands.

## Phase 7 - Verification

- [x] T701 Run `uv run --extra dev pytest tests/unit/ -v`.
- [x] T702 Run `uv run --extra dev ruff check .`.
- [x] T703 Manually run `morphic chat`, `/status`, `/context`, `/quit`.
- [x] T704 Verify `.morphic/sessions/*.jsonl` is append-only.
- [x] T705 Verify `.morphic/context/index.json` includes `AGENTS.md` and `CLAUDE.md`.
- [x] T706 Verify existing `.claude/` files are not modified by scan.

## Phase 8 - Route-backed Engine Registry

- [x] T801 Add `RouteEngineRegistry` adapter from `RouteToEngineUseCase` statuses to chat `EngineProfile`.
- [x] T802 Map agent engine runtime kind, availability, context window, sandbox, streaming, editing, JSON output, and cost profile.
- [x] T803 Allow `morphic chat --doctor` payloads to use an injected or live engine registry.
- [x] T804 Allow `ChatRepl` slash commands to use an injected or live engine registry.
- [x] T805 Preserve `StaticEngineRegistry` fallback when the live route container is unavailable.

## Phase 9 - Route-backed Council Runtime

- [x] T901 Add `RouteChatCouncilRuntime` adapter from `RouteToEngineUseCase` to `CouncilRuntimePort`.
- [x] T902 Delegate planner, critic, and leader role prompts through route execution with normalized `CouncilTurn` output.
- [x] T903 Preserve local deterministic council fallback on route failure, empty output, exceptions, or missing opt-in.
- [x] T904 Allow `ChatRepl` to accept injected council runtimes for tests and future routing.
- [x] T905 Gate live route-backed chat council execution behind `MORPHIC_CHAT_ROUTE_COUNCIL=1`.

## Phase 10 - Routed Council CLI Opt-In

- [x] T1001 Add `morphic chat --route-council`.
- [x] T1002 Add `morphic code --route-council`.
- [x] T1003 Preserve default local council behavior when the flag and env var are absent.
- [x] T1004 Preserve `MORPHIC_CHAT_ROUTE_COUNCIL=1` env opt-in.
- [x] T1005 Unit test route-council flags without invoking real route engines.

## Phase 11 - Routed Council Role Preferences

- [x] T1101 Add role-to-engine preferences to `RouteChatCouncilRuntime`.
- [x] T1102 Pass planner, critic, and leader preferred engines to `RouteToEngineUseCase.execute`.
- [x] T1103 Add `--planner-engine`, `--critic-engine`, and `--leader-engine` CLI options for `morphic chat`.
- [x] T1104 Add `--planner-engine`, `--critic-engine`, and `--leader-engine` CLI options for `morphic code`.
- [x] T1105 Unit test role preferences without invoking real route engines.

## Phase 12 - Routed Council Diagnostics

- [x] T1201 Validate routed council role engine ids before constructing route runtime.
- [x] T1202 Return user-facing CLI diagnostics for invalid planner, critic, or leader engine ids.
- [x] T1203 Preserve exit code 2 for invalid non-interactive routed council options.
- [x] T1204 Ensure invalid role engine ids are not hidden by local council fallback.

## Phase 13 - Hook Diagnostics

- [x] T1301 Add read-only `.morphic/hooks/*.json` hook validation.
- [x] T1302 Validate hook type, command, enabled flag, and secret-path risk posture.
- [x] T1303 Add `morphic doctor hooks`.
- [x] T1304 Add `morphic doctor hooks --json`.
- [x] T1305 Preserve stable exit codes: FAIL exits 1, WARN exits 0.

## Phase 14 - Hook Execution Planning

- [x] T1401 Add hook domain definitions and a hook registry port for validated hook metadata.
- [x] T1402 Add chat event types for hook execution planned/skipped ledger entries.
- [x] T1403 Add `PlanChatHooksUseCase` that records hook plans without executing commands.
- [x] T1404 Extend `WorkspaceHookRegistry` with `hooks_for()` domain definitions.
- [x] T1405 Block hook planning when hook diagnostics contain FAIL results.

## Phase 15 - Hook Planning in Tool Harness

- [x] T1501 Allow `ExecuteChatToolUseCase` to accept an optional hook planner.
- [x] T1502 Record `pre_tool` hook plan events before tool execution.
- [x] T1503 Record `post_tool` hook plan events after tool execution.
- [x] T1504 Preserve existing tool execution behavior when no hook planner is injected.
- [x] T1505 Preserve append-only session ledger ordering across hook/tool/verification events.

## Phase 16 - Hook Execution Use Case

- [x] T1601 Add hook execution request/result domain models.
- [x] T1602 Add `HookExecutorPort` for approved hook command execution.
- [x] T1603 Add `hook_execution_requested` and `hook_execution_completed` ledger events.
- [x] T1604 Add `ExecuteChatHookUseCase` that executes enabled hooks through the port.
- [x] T1605 Record disabled hooks as skipped without calling the executor.
- [x] T1606 Block hook execution when hook diagnostics contain FAIL results.
- [x] T1607 Keep shell-backed hook execution infrastructure deferred until approval/risk policy is wired.

## Phase 17 - Hook Runner Wiring

- [x] T1701 Add a no-op `HookExecutorPort` infrastructure adapter for safe wiring.
- [x] T1702 Allow `ExecuteChatToolUseCase` to accept an optional `ExecuteChatHookUseCase`.
- [x] T1703 Execute `pre_tool` hooks before tool execution when a hook runner is injected.
- [x] T1704 Execute `post_tool` hooks after tool execution when a hook runner is injected.
- [x] T1705 Preserve existing hook planning behavior when only a hook planner is injected.
- [x] T1706 Preserve append-only session ledger ordering across hook execution/tool/verification events.
- [x] T1707 Keep real shell-backed hook command execution deferred.

## Phase 18 - Shell-backed Hook Executor

- [x] T1801 Add `ShellHookExecutor` that maps hook commands to LAEE `shell_exec` actions.
- [x] T1802 Run hook shell commands with workspace root as `cwd` and configurable timeout.
- [x] T1803 Normalize LAEE success observations into successful hook execution results.
- [x] T1804 Normalize LAEE denied/error observations into failed hook execution results.
- [x] T1805 Stop tool execution when an injected `pre_tool` hook runner records a failed hook result.
- [x] T1806 Preserve post-tool hook failure as ledger data without adding rollback behavior.

## Phase 19 - Hook Execution Mode Wiring

- [x] T1901 Add chat hook executor factory with safe no-op default.
- [x] T1902 Select shell-backed hook execution only when `MORPHIC_CHAT_HOOK_EXECUTION=shell`.
- [x] T1903 Reject unknown hook execution modes with user-facing validation.
- [x] T1904 Build shell hook executor with LAEE local executor settings when opt-in is enabled.
- [x] T1905 Surface hook execution mode in `morphic chat --doctor --json`.

## Phase 20 - Manual Hook Run CLI

- [x] T2001 Add `morphic hooks run <hook_type>` for explicit hook execution.
- [x] T2002 Persist manual hook execution events to `.morphic/sessions/*.jsonl`.
- [x] T2003 Emit JSON output for automation via `morphic hooks run <hook_type> --json`.
- [x] T2004 Preserve safe no-op default for manual hook runs.
- [x] T2005 Validate shell opt-in execution with `MORPHIC_CHAT_HOOK_EXECUTION=shell`.
- [x] T2006 Confirm shell opt-in writes LAEE audit log entries.

## Phase 21 - REPL Hook Run UX

- [x] T2101 Add `/hooks run <hook_type>` handling inside `morphic chat`.
- [x] T2102 Record REPL hook run slash commands in the current chat session ledger.
- [x] T2103 Record REPL hook execution events in the current chat session ledger.
- [x] T2104 Preserve no-op default for REPL hook runs.
- [x] T2105 Respect `MORPHIC_CHAT_HOOK_EXECUTION=shell` for REPL hook runs.
- [x] T2106 Validate shell opt-in REPL hook execution writes LAEE audit log entries.

## Phase 22 - REPL Tool Run No-op UX

- [x] T2201 Add `NoopToolExecutor` as a safe default chat tool executor.
- [x] T2202 Add `/tools run <tool_name> [json_arguments]` handling inside `morphic chat`.
- [x] T2203 Record REPL tool run slash commands in the current chat session ledger.
- [x] T2204 Route REPL tool runs through `ExecuteChatToolUseCase`.
- [x] T2205 Inject existing hook runner flow around REPL tool runs.
- [x] T2206 Preserve no-op default so explicit `/tools run` does not mutate the workspace.
- [x] T2207 Reject invalid JSON tool arguments with a user-facing message.

## Phase 23 - REPL Tool Run LAEE Opt-In

- [x] T2301 Add chat tool executor factory with safe no-op default.
- [x] T2302 Select LAEE-backed tool execution only when `MORPHIC_CHAT_TOOL_EXECUTION=laee`.
- [x] T2303 Reject unknown tool execution modes with user-facing validation.
- [x] T2304 Build LAEE tool executor with shared local executor settings when opt-in is enabled.
- [x] T2305 Surface tool execution mode in `morphic chat --doctor --json`.
- [x] T2306 Validate REPL `/tools run shell_exec ...` writes LAEE audit log entries when opted in.

## Deferred

- [ ] D001 Textual full-screen TUI.
- [ ] D002 Claude Code adapter.
- [ ] D003 Gemini CLI adapter.
- [ ] D004 Codex CLI adapter.
- [ ] D005 OpenHands adapter.
- [ ] D006 `.morphic` to `.claude` export.
- [ ] D007 `.morphic` to Gemini/Codex metadata export.
- [x] D008 Hook command execution.
- [ ] D009 Council event visualization.
- [ ] D010 Memory candidate approval UI.
- [ ] D011 General chat tool execution UX beyond explicit hook commands.
