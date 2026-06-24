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

## Deferred

- [ ] D001 Textual full-screen TUI.
- [ ] D002 Claude Code adapter.
- [ ] D003 Gemini CLI adapter.
- [ ] D004 Codex CLI adapter.
- [ ] D005 OpenHands adapter.
- [ ] D006 `.morphic` to `.claude` export.
- [ ] D007 `.morphic` to Gemini/Codex metadata export.
- [ ] D008 Hook validation and execution.
- [ ] D009 Council event visualization.
- [ ] D010 Memory candidate approval UI.
