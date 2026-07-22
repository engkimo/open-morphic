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

## Phase 24 - REPL Tool Run Failure Reporting

- [x] T2401 Report LAEE denied/error tool results with `success=False` and `exit_code`.
- [x] T2402 Surface LAEE failure stderr summaries in `/tools run` output.
- [x] T2403 Assess `/tools run` risk from tool name and JSON arguments before execution.
- [x] T2404 Validate denied destructive tools keep the target file intact and write audit logs.

## Phase 25 - CLI Permission Mode Controls

- [x] T2501 Add `--permission-mode` to `morphic chat`.
- [x] T2502 Add `--permission-mode` to `morphic code`.
- [x] T2503 Persist selected permission mode in session start ledger events.
- [x] T2504 Surface selected permission mode through `/status`.
- [x] T2505 Keep read-only tool blocking user-facing instead of crashing the REPL.

## Phase 26 - Single-Engine Direct Route

- [x] T2601 Add RED tests for one-call route-backed direct runtime behavior.
- [x] T2602 Add `RouteChatDirectRuntime` and normalize its result as one implementer turn.
- [x] T2603 Add `--route-direct` to `morphic chat` and `morphic code`.
- [x] T2604 Add optional `--engine <engine_id>` preference for direct mode.
- [x] T2605 Reject simultaneous `--route-direct` and `--route-council` modes.
- [x] T2606 Surface route failure and empty output without local success fallback.
- [x] T2607 Require explicit `danger-full-access` until native permission mapping exists.
- [x] T2608 Keep external engines fake-only in unit tests.

## Phase 27 - Codex Permission and JSONL Normalization

- [x] T2701 Add strict provider-independent native engine event entities.
- [x] T2702 Parse Codex JSONL thread, turn, item, completion, failure, and error records.
- [x] T2703 Extract Codex thread id, final assistant message, usage, and parse diagnostics.
- [x] T2704 Replace deprecated `--full-auto` with explicit `--sandbox`.
- [x] T2705 Map read-only, workspace-write, and danger-full-access permissions to Codex.
- [x] T2706 Reject confirm-destructive because non-interactive Codex cannot prompt.
- [x] T2707 Pass workspace root with Codex `--cd`.
- [x] T2708 Restrict direct route to explicit `--engine codex_cli` until other mappings exist.
- [x] T2709 Preserve legacy single-JSON/raw-output parsing compatibility.

## Phase 28 - Native Event Ledger and Scoped Execution Contract

- [x] T2801 Attach normalized native engine events to direct-runtime turns.
- [x] T2802 Persist each native engine event as an append-only `engine_event` chat event.
- [x] T2803 Preserve native event order before the corresponding council argument.
- [x] T2804 Add a separate `ScopedAgentEnginePort` for workspace and permission-aware execution.
- [x] T2805 Keep the common `AgentEnginePort` compatible with existing engine adapters.
- [x] T2806 Skip permission-unaware engines instead of silently dropping scoped controls.
- [x] T2807 Retain raw provider payloads in the session ledger for audit and replay.

## Phase 29 - Incremental Codex Event Streaming

- [x] T2901 Add an async subprocess runner that drains stdout and stderr concurrently.
- [x] T2902 Deliver decoded stdout lines before native process completion.
- [x] T2903 Add a stateful Codex JSONL event decoder for sequence and thread propagation.
- [x] T2904 Add explicit streaming scoped-engine and council runtime capability ports.
- [x] T2905 Route streaming scoped requests only to adapters that implement the capability.
- [x] T2906 Persist user input before execution and native events as they arrive.
- [x] T2907 Avoid replaying streamed result metadata into duplicate ledger events.
- [x] T2908 Preserve buffered execution for non-streaming callers and adapters.

## Phase 30 - Live Native Progress Rendering

- [x] T3001 Add an optional native event observer to send-message orchestration.
- [x] T3002 Publish to the observer only after durable ledger append succeeds.
- [x] T3003 Keep observer failures best-effort so presentation cannot erase audit state.
- [x] T3004 Add a concise terminal renderer for selected lifecycle/tool/file/plan events.
- [x] T3005 Suppress assistant-message, unknown, raw payload, and reasoning content.
- [x] T3006 Compact whitespace and cap rendered event detail length.
- [x] T3007 Wire the renderer into Chat REPL and one-shot code streaming paths.

## Phase 31 - Scoped Codex Thread Resume

- [x] T3101 Track native session id, engine, workspace, and permission provenance.
- [x] T3102 Restore native session provenance by replaying the append-only ledger.
- [x] T3103 Add a narrow resumable streaming engine capability port.
- [x] T3104 Route an explicit native session id only to resumable adapters.
- [x] T3105 Invoke `codex exec ... resume <thread_id> <prompt>` with explicit sandbox and cwd.
- [x] T3106 Reuse the stored Codex thread on later turns in the same Morphic session.
- [x] T3107 Refuse resume when workspace or permission provenance does not match.
- [x] T3108 Reject native resume requests missing streaming/scope context.

## Phase 34 - Claude Native Streaming and Resume

- [x] T3401 Normalize Claude system init, assistant, user, tool, and result JSONL.
- [x] T3402 Retain raw Claude payloads and explicit session ids in native events.
- [x] T3403 Implement scoped Claude stream-json delivery through the shared event sink.
- [x] T3404 Resume an explicit Claude session id under stored workspace/permission scope.
- [x] T3405 Preserve Claude-reported final output, model, usage, and total cost.
- [x] T3406 Allow `--engine claude_code` in route-direct Chat CLI mode.

## Phase 35 - Provider-Pinned Native Resume

- [x] T3501 Require the native owner engine with every resume session id.
- [x] T3502 Reject preferred-engine and resume-engine mismatches.
- [x] T3503 Skip non-owner engines before availability checks or execution.
- [x] T3504 Prevent cross-provider fallback with a provider-native session id.
- [x] T3505 Record resume-engine mismatch attempts for routing transparency.

## Phase 36 - Durable Turn Cancellation

- [x] T3601 Add RED tests for interrupted streaming-turn persistence.
- [x] T3602 Append `turn_cancelled` after all native events delivered before cancellation.
- [x] T3603 Re-raise the original asyncio cancellation after the ledger append.
- [x] T3604 Report Ctrl-C consistently for chat and code with exit code 130.
- [x] T3605 Verify cancellation behavior without invoking a real native CLI.

## Phase 37 - Active Turn Control

- [x] T3701 Add RED tests for active-turn cancellation and outer cancellation passthrough.
- [x] T3702 Add an injectable controller that owns at most one turn task.
- [x] T3703 Route SIGINT to the active child task and restore the previous handler.
- [x] T3704 Ignore repeated cancellation requests while cleanup is already running.
- [x] T3705 Replay the ledger before the interactive REPL accepts another prompt.
- [x] T3706 Preserve idle and one-shot process-level Ctrl-C behavior.
- [x] T3707 Verify continuous ledger sequencing after cancellation and REPL continuation.
- [x] T3708 Persist user input and cancellation for non-streaming runtimes too.

## Phase 38 - Authenticated Loopback Control

- [x] T3801 Add RED tests for external status/cancel and descriptor cleanup.
- [x] T3802 Bind a short-lived server only to `127.0.0.1` on a random port.
- [x] T3803 Write a protocol-versioned session descriptor with 0700/0600 permissions.
- [x] T3804 Authenticate requests with a random token and exact session id.
- [x] T3805 Reject non-loopback descriptors and unsupported commands fail closed.
- [x] T3806 Add explicit `morphic chat --control` opt-in wiring.
- [x] T3807 Add `morphic chat-control status/cancel` with single-session discovery.
- [x] T3808 Remove owned descriptors after completion or cancellation cleanup.

## Phase 39 - Provider-Neutral Steering

- [x] T3901 Add RED tests for bounded steer queueing and native-session continuation.
- [x] T3902 Accept only non-empty replacement prompts up to 2048 UTF-8 bytes.
- [x] T3903 Make steer queue first-writer-wins during cancellation cleanup.
- [x] T3904 Add authenticated `steer` to the loopback protocol and client CLI.
- [x] T3905 Replay the ledger before submitting the replacement prompt.
- [x] T3906 Append `turn_steered` metadata before the replacement `user_message`.
- [x] T3907 Preserve provider, workspace, and permission provenance through resume.
- [x] T3908 Treat slash-prefixed replacement prompts as provider messages.

## Phase 40 - Recorded Same-Task Agent CLI Benchmark

- [x] T4001 Add RED tests for the manifest, complete trial matrix, metrics, and CLI.
- [x] T4002 Require Codex, Claude Code, and Morphic-controlled arms on one task revision.
- [x] T4003 Derive verification and handoff fidelity from predeclared assertions.
- [x] T4004 Reject duplicate, missing, mismatched, and undeclared observations.
- [x] T4005 Report metric-specific leaders without a subjective composite score.
- [x] T4006 Emit deterministic timestamp-free JSON for review and CI artifacts.
- [x] T4007 Keep agent launch and paid live execution outside the offline evaluator.
- [x] T4008 Include the benchmark package in built distributions.

## Phase 41 - Explicit Opt-in Isolated Trial Recorder

- [x] T4101 Add RED tests for plan, consent, isolation, cleanup, evidence, and CLI.
- [x] T4102 Require exact arm/check/handoff command coverage for the Phase 40 manifest.
- [x] T4103 Make read-only deterministic planning the default behavior.
- [x] T4104 Require execute, paid acknowledgement, and an explicit estimate cost cap.
- [x] T4105 Run every arm/trial in a unique detached worktree outside the source root.
- [x] T4106 Pass argv without a shell and terminate commands at the configured timeout.
- [x] T4107 Remove worktrees after success, command failure, or recorder exceptions.
- [x] T4108 Persist hashes/byte counts/outcomes without raw prompts or command output.
- [x] T4109 Refuse existing evidence output and write new evidence atomically.
- [x] T4110 Keep actual cost and accepted-patch decisions pending explicit adjudication.

## Phase 42 - Provider Receipts and Deterministic Adjudication

- [x] T4201 Add RED tests for receipt parsing, evidence joins, failures, and CLI output.
- [x] T4202 Normalize Codex usage with model-hinted deterministic cost calculation.
- [x] T4203 Normalize Claude provider-reported cost without retaining result text.
- [x] T4204 Define a strict Morphic benchmark receipt envelope.
- [x] T4205 Persist normalized receipts only when parsing succeeds for every trial.
- [x] T4206 Bind independent review decisions to agent argv fingerprints.
- [x] T4207 Recompute machine check/handoff outcomes instead of trusting copied lists.
- [x] T4208 Reject missing/duplicate/mismatched/parse-error/over-cap campaigns.
- [x] T4209 Reject accepted-patch review for provider or process failure.
- [x] T4210 Emit exclusive deterministic Phase 40 result JSON without live execution.

## Phase 43 - First-party Receipt and Zero-cost Rehearsal

- [x] T4301 Add RED tests for Morphic receipt output and local rehearsal publication.
- [x] T4302 Add explicit `morphic code --benchmark-receipt` without changing defaults.
- [x] T4303 Aggregate council cost and normalized non-negative usage only.
- [x] T4304 Fail closed without a receipt when failure/cancellation cost is unknown.
- [x] T4305 Commit parseable manifest and recorder configuration examples.
- [x] T4306 Generate internal-only zero-cost fixtures for all three provider shapes.
- [x] T4307 Exercise recorder isolation, receipt parsing, review joins, and finalization.
- [x] T4308 Keep synthetic accepted-patch decisions false and cost exactly zero.
- [x] T4309 Publish a complete rehearsal bundle without replacing existing output.
- [x] T4310 Verify a real pinned-worktree rehearsal leaves no raw output or worktree.

## Phase 44 - Campaign Preflight and Bound Reviews

- [x] T4401 Add RED tests for preflight, review templates, bindings, and CLI output.
- [x] T4402 Require the manifest revision to equal a full resolved Git commit.
- [x] T4403 Require exact runtime version declarations matching all three executables.
- [x] T4404 Normalize and fingerprint runtime versions without executing version commands.
- [x] T4405 Reuse deterministic arm/check/handoff command fingerprints.
- [x] T4405a Bind complete manifest/config contracts without exposing the raw goal.
- [x] T4406 Emit a self-fingerprinted preflight with `execution_authorized=false`.
- [x] T4407 Generate null review decisions for the complete expected trial matrix.
- [x] T4408 Bind reviews to preflight, evidence, and expanded agent argv fingerprints.
- [x] T4409 Validate bindings during finalization while accepting legacy unbound reviews.
- [x] T4410 Verify the complete preflight/template path with a zero-cost local campaign.

## Phase 45 - Reviewer Separation and Campaign Status

- [x] T4501 Add RED tests for reviewer policy, lifecycle stages, failures, and CLI.
- [x] T4502 Normalize and fingerprint operator/reviewer policy declarations.
- [x] T4503 Reject operator self-review and reviewer IDs outside the allowlist.
- [x] T4504 Enforce minimum distinct reviewers and reject impossible policy capacity.
- [x] T4505 Bind policy SHA-256 into pending and completed review artifacts.
- [x] T4506 Add six deterministic manifest-to-finalized lifecycle stages.
- [x] T4507 Validate artifact order, identity, hashes, estimates, policy, and results.
- [x] T4508 Keep campaign status read-only and non-authorizing at every stage.
- [x] T4509 Preserve legacy review/finalize behavior when no policy binding exists.
- [x] T4510 Verify zero-cost review-pending status without artifact mutation.

## Phase 46 - Signed Reviewer Provenance

- [x] T4601 Add RED tests for reviewer trust, signing payloads, signature failures, and CLI paths.
- [x] T4602 Normalize Ed25519 public keys and self-fingerprint the reviewer trust declaration.
- [x] T4603 Bind reviewer trust to the exact benchmark and Phase 45 review policy.
- [x] T4604 Require an active key for each allowed reviewer while retaining revoked keys.
- [x] T4605 Bind completed reviews and each reviewer's decision subset into canonical payloads.
- [x] T4606 Generate signing requests without reading or persisting reviewer private keys.
- [x] T4607 Require one valid active-key signature per distinct reviewer.
- [x] T4608 Reject invalid/revoked/unknown signatures, missing coverage, and mixed artifacts.
- [x] T4609 Add attestation-pending campaign status and trust-bound finalize enforcement.
- [x] T4610 Preserve the unsigned legacy campaign path and verify distribution contents.

## Phase 47 - Authority-Anchored Campaign Provenance

- [x] T4701 Add RED tests for authority identity, enrollment, envelopes, failures, and CLI.
- [x] T4702 Normalize and self-fingerprint an offline Ed25519 organization authority.
- [x] T4703 Bind anchored reviewer trust to the exact authority fingerprint.
- [x] T4704 Generate private-key-free enrollment signing requests for every reviewer key.
- [x] T4705 Verify exactly one authority certificate for every retained trust key.
- [x] T4706 Reject invalid signatures, missing coverage, duplicates, and mixed trust artifacts.
- [x] T4707 Require authority enrollment during anchored finalization and status validation.
- [x] T4708 Bind the complete finalized artifact chain into one non-authorizing envelope.
- [x] T4709 Require the authority envelope signature before anchored campaign finalization.
- [x] T4710 Preserve unanchored and unsigned paths and verify distribution contents.

## Phase 48 - Authority-Root Continuity and Transparency

- [x] T4801 Add RED tests for root rotation, revocation, Merkle proofs, lifecycle, and CLI.
- [x] T4802 Require contiguous root generations signed by each immediate predecessor.
- [x] T4803 Self-fingerprint and active-root-sign the complete root ledger and revocations.
- [x] T4804 Reject reused roots, unknown revocations, invalid rotations, and revoked active roots.
- [x] T4805 Bind reviewer trust, finalization, and campaign envelopes to the exact root ledger.
- [x] T4806 Build RFC 6962-style domain-separated Merkle roots and inclusion audit paths.
- [x] T4807 Sign tree heads with the ledger's active root and verify exact envelope inclusion.
- [x] T4808 Verify append-only complete-log growth through exact prefix preservation.
- [x] T4809 Add private-key-free rotation/ledger/tree-head and offline log/proof CLI paths.
- [x] T4810 Preserve Phase 47 and unsigned legacy hashes, signatures, and lifecycle behavior.

## Phase 49 - Compact Consistency and Witness Checkpoints

- [x] T4901 Add RED tests for compact proofs, witness quorum, split views, lifecycle, and CLI.
- [x] T4902 Generate the unique minimal RFC 6962 consistency path with `SUBPROOF` recursion.
- [x] T4903 Reconstruct and verify both signed roots without complete log artifacts.
- [x] T4904 Reject mismatched log IDs, ledgers, sizes, paths, roots, and tree-head signatures.
- [x] T4905 Normalize and self-fingerprint Ed25519 witness trust with active/revoked keys.
- [x] T4906 Require a strict-majority distinct-witness quorum for checkpoint acceptance.
- [x] T4907 Bind witness signatures to old/new heads, root ledger, proof, and witness trust.
- [x] T4908 Detect same-size different-root witnessed split views.
- [x] T4909 Add offline consistency, witness-trust, and checkpoint-template CLI paths.
- [x] T4910 Preserve Phase 48 inclusion-only and all earlier campaign lifecycle behavior.

## Phase 50 - Durable Checkpoint Registry and Authenticated Peer Exchange

- [x] T5001 Add RED tests for registry replay, concurrent append, peer packets, and CLI.
- [x] T5002 Store deterministic self-fingerprinted checkpoint records in hash-chained JSONL.
- [x] T5003 Replay and verify every sequence, record hash, proof, signature, and trust binding.
- [x] T5004 Serialize append with file locking, `O_APPEND`, `fsync`, and mode 0600.
- [x] T5005 Reject stale extensions, sequence gaps, chain tampering, and witnessed split views.
- [x] T5006 Normalize self-fingerprinted peer Ed25519 trust with active/revoked key rotation.
- [x] T5007 Sign exact registry records and authenticate the source peer before import.
- [x] T5008 Make duplicate local append and authenticated packet retry idempotent.
- [x] T5009 Add offline peer-trust, registry status/store/export/import CLI paths.
- [x] T5010 Preserve private-key-free operation and avoid external agents, services, or APIs.

## Phase 51 - Authenticated Range Sync and Peer Cursors

- [x] T5101 Add RED tests for signed ranges, overlap/gap handling, acknowledgements, cursors, and CLI.
- [x] T5102 Bind a bounded contiguous record range and its base/head hashes to one peer signature.
- [x] T5103 Authenticate and validate every range record before acquiring the destination write lock.
- [x] T5104 Compare existing overlaps exactly and append only a contiguous missing suffix.
- [x] T5105 Roll back process-level write failures to the original registry size before releasing the lock.
- [x] T5106 Bind receiver acknowledgements to the exact signed range and applied registry head.
- [x] T5107 Store verified acknowledgements in a mode 0600 hash-chained peer cursor ledger.
- [x] T5108 Enforce monotonic per-peer cursors and reject regression, conflict, tampering, and invalid signatures.
- [x] T5109 Add private-key-free range export/import, acknowledgement-template, and cursor CLI paths.
- [x] T5110 Preserve single-record exchange and keep all network/paid execution disabled.

## Phase 52 - Peer-Trust Rollover Continuity

- [x] T5201 Add RED tests for rollover quorum, generation replay, resolver, historical cursors, and CLI.
- [x] T5202 Bind registry, generation, predecessor/successor trust, and computed quorum in one statement.
- [x] T5203 Emit one private-key-free signing request per active predecessor peer.
- [x] T5204 Require a strict majority of distinct predecessor peers with active trusted Ed25519 keys.
- [x] T5205 Reject minority, duplicate peers, successor-only/revoked keys, invalid signatures, and trust reuse.
- [x] T5206 Build a contiguous self-fingerprinted generation ledger from out-of-band genesis.
- [x] T5207 Resolve historical trust fingerprints so old and new acknowledgements replay together.
- [x] T5208 Extend cursor store/status to accept exactly one trust snapshot or trust ledger.
- [x] T5209 Add peer-trust rotation-template and generation-ledger CLI paths.
- [x] T5210 Preserve offline/private-key-free behavior and defer network transport.

## Deferred

- [ ] D001 Textual full-screen TUI.
- [x] D002 Claude Code adapter.
- [ ] D003 Gemini CLI adapter.
- [x] D004 Codex CLI adapter.
- [ ] D005 OpenHands adapter.
- [ ] D006 `.morphic` to `.claude` export.
- [ ] D007 `.morphic` to Gemini/Codex metadata export.
- [x] D008 Hook command execution.
- [ ] D009 Council event visualization.
- [ ] D010 Memory candidate approval UI.
- [ ] D011 General chat tool execution UX beyond explicit hook commands.
- [ ] D012 Native CLI streaming, resume, steering, and permission propagation.
