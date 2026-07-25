# Feature Specification - Morphic Chat CLI

> **Branch:** `feature/morphic-chat-cli`
> **Status:** draft
> **Owner:** Ryousuke
> **Created:** 2026-06-24

## Problem Statement

Developers increasingly switch between Claude Code, Gemini CLI, Codex CLI, OpenHands, and local models to get the best current model or agent runtime for each task. The switching cost is high: each tool has its own chat surface, instruction files, memory, hooks, approvals, harness behavior, session history, and metadata conventions.

Morphic already has engine routing, LAEE, semantic memory direction, and a council pilot. What is missing is a first-party terminal chat experience that feels like modern agentic coding CLIs while making Morphic the control plane for multi-engine, multi-agent work.

The goal is not to create another single-engine CLI. The goal is to create a Morphic terminal chat CLI where the user, Morphic, and multiple agent roles can discuss, execute, verify, and reflect on coding tasks through one persistent workspace harness.

## Product Thesis

Morphic Chat CLI is a terminal-native, chat-based development interface backed by a multi-engine council runtime and canonical workspace metadata.

```
User:
  describes goals, constraints, approvals, corrections

Morphic Chat CLI:
  owns the terminal UX, session state, memory, policy, approvals, tool log, diff preview, and final decision

Council Runtime:
  planner, architect, implementer, critic, tester, leader, reflector

Execution Engines:
  Claude Code, Gemini CLI, Codex CLI, OpenHands, Ollama, direct LLM gateway
```

## Goals

- Provide a first-party terminal chat UI via `morphic chat` that supports conversational task execution, interruption, approval, resume, and structured status.
- Centralize agent workspace metadata in `.morphic/` and treat `.claude/`, `AGENTS.md`, `GEMINI.md`, Codex config, and other tool-specific files as import/export projections where possible.
- Support multi-agent deliberation in the CLI: planner/implementer/critic/leader roles can produce and compare plans before execution.
- Preserve user control: destructive actions, broad edits, shell commands, and commit/push operations remain governed by LAEE risk classification and approval policy.
- Produce a durable session ledger in `.morphic/sessions/*.jsonl` that records user turns, assistant turns, council events, tool calls, approvals, diffs, command results, and final summaries.
- Match operational expectations of modern agentic coding CLIs: slash commands, doctor/status output, session resume, permission modes, hook validation, tool registry, structured automation output.

## Non-Goals

- No cloning of Claude Code, Gemini CLI, Codex CLI, or claw-code internals. External projects are reference material for UX and operational expectations only.
- No direct copy of prompts, code, private schemas, or leaked implementation details from any third-party CLI.
- No replacement of existing deterministic routing in the first sprint. Existing routing stays available as a fallback.
- No full-screen TUI dependency in the first MVP if a simpler REPL can validate the loop faster.
- No multi-repo cloud service in the MVP. The first version is local workspace first.
- No automatic commit or push without explicit user approval.

## User Stories

### As a developer using multiple AI coding CLIs, I want one Morphic terminal chat interface, so that I do not have to choose Claude Code, Gemini CLI, or Codex CLI manually for every task.

Acceptance criteria:
- [ ] Running `morphic chat` starts an interactive terminal session in the current workspace.
- [ ] The user can submit a natural-language goal and receive a plan before edits occur.
- [ ] Morphic records which engine or role contributed to each plan or decision.
- [ ] The user can interrupt and revise constraints during the session.

### As a developer with existing `.claude/`, `AGENTS.md`, and project docs, I want Morphic to discover and normalize workspace instructions, so that agent behavior does not diverge across tools.

Acceptance criteria:
- [ ] `morphic chat` discovers root `AGENTS.md`, `CLAUDE.md`, `.claude/agents`, `.claude/skills`, `.claude/commands`, `.claude/rules`, `GEMINI.md`, and `.morphic/` when present.
- [ ] Discovery produces a structured context index under `.morphic/context/index.json`.
- [ ] The CLI shows source provenance for imported rules in `/context`.
- [ ] The system never edits existing instruction files during discovery unless the user runs an explicit sync/export command.

### As a user supervising an agentic coding task, I want to see proposed edits, shell commands, risk levels, and approvals inline, so that I can trust the automation without giving up control.

Acceptance criteria:
- [ ] Before file edits, Morphic presents a concise diff preview or edit summary.
- [ ] Before risky shell commands, Morphic presents risk level, reason, and approval options.
- [ ] LAEE audit events are appended for tool actions that mutate local state.
- [ ] `/diff`, `/tools`, and `/approvals` show current session state.

### As a reviewer of Morphic itself, I want the feature to respect Clean Architecture, so that the CLI UX does not leak infrastructure into domain logic.

Acceptance criteria:
- [ ] `domain/` additions import no FastAPI, SQLAlchemy, LiteLLM, Textual, Rich, Typer, subprocess, or infrastructure modules.
- [ ] `application/` use cases depend only on domain entities/ports and application DTOs.
- [ ] Terminal rendering lives in `interface/cli/`.
- [ ] Engine adapters and local execution implementations live under `infrastructure/`.

## Functional Requirements

- **FR-1:** The system shall add `morphic chat` as an interactive terminal command.
- **FR-2:** The system shall add `morphic code "<goal>"` as a one-shot entry that starts from a goal and may continue into the chat loop when user input is required.
- **FR-3:** The chat session shall persist append-only events to `.morphic/sessions/<session_id>.jsonl`.
- **FR-4:** The session event stream shall include at minimum: `user_message`, `assistant_message`, `council_event`, `tool_call_requested`, `tool_call_completed`, `approval_requested`, `approval_resolved`, `diff_proposed`, `verification_result`, `session_summary`.
- **FR-5:** The CLI shall expose slash commands: `/help`, `/status`, `/doctor`, `/context`, `/memory`, `/engines`, `/council`, `/tools`, `/diff`, `/approvals`, `/resume`, `/export`, `/quit`.
- **FR-6:** The system shall discover workspace instruction sources and build `.morphic/context/index.json` with source path, source type, precedence, hash, and imported sections.
- **FR-7:** The system shall support a canonical `.morphic/` layout for context, memory, hooks, sessions, and exports.
- **FR-8:** The system shall provide import-only discovery before export/sync exists. Export to `.claude/`, `AGENTS.md`, `GEMINI.md`, and Codex config is a follow-up unless explicitly enabled.
- **FR-9:** The system shall model council roles separately from engine adapters. A role is a deliberation responsibility; an engine is an execution/runtime backend.
- **FR-10:** The MVP council shall support four roles: planner, implementer, critic, leader.
- **FR-11:** The leader shall select plans by evidence: project rules, architecture constraints, testability, minimality, cost, latency, security risk, and verification results.
- **FR-12:** The execution harness shall route local file/shell/git actions through existing LAEE or LAEE-compatible ports.
- **FR-13:** The CLI shall support permission modes compatible with Morphic policy: `read-only`, `workspace-write`, `confirm-destructive`, `danger-full-access`.
- **FR-14:** The CLI shall support structured non-interactive output for diagnostics: `morphic chat --doctor --json` or equivalent.
- **FR-15:** The system shall resume the latest session with `morphic chat --resume latest`.
- **FR-16:** The CLI shall offer an explicit single-engine direct route that invokes `RouteToEngineUseCase` exactly once per user turn instead of forcing planner/critic/leader council execution.
- **FR-17:** The direct route shall accept an optional preferred engine id and shall surface route failure or empty output instead of silently returning a deterministic local response as success.
- **FR-18:** Direct external-engine execution shall propagate workspace root and Morphic permission mode to a native adapter that can preserve them. Codex direct mode maps `read-only`, `workspace-write`, and `danger-full-access` to explicit Codex sandboxes and rejects `confirm-destructive`, because non-interactive execution cannot surface a new approval prompt.
- **FR-19:** Native JSONL engine output shall be normalized into provider-independent engine events while retaining the raw provider payload for audit and forward compatibility.
- **FR-20:** A direct native run shall persist each normalized engine event as an independent append-only session event, in provider order and before the corresponding council argument and assistant response.
- **FR-21:** Workspace root and permission mode shall be passed only through adapters that explicitly implement scoped execution; routing shall skip unsupported adapters rather than silently discarding either control.
- **FR-22:** A streaming native adapter shall publish normalized events and append them to the session ledger before the native process exits; final buffered metadata shall not duplicate events already persisted through the stream.
- **FR-23:** The terminal shall render a concise allowlist of live native lifecycle, tool, file, and plan events after durable append. It shall not render raw provider payloads, hidden reasoning, or duplicate the final assistant message as progress.
- **FR-24:** Native session resume shall bind the provider session id to its engine, original workspace root, and permission mode. Resume shall use an explicit resumable adapter capability and shall fail closed when any safety provenance differs or is absent.
- **FR-25:** Claude Code direct mode shall preserve its native project harness while normalizing `stream-json` init, assistant, tool use/result, and final result messages into the same Morphic event and scoped-resume contracts as Codex.
- **FR-26:** A native resume session id shall be pinned to its originating engine. Routing shall never pass a Claude session id to Codex, a Codex thread id to Claude, or any provider-native id to a fallback engine.
- **FR-27:** Cancelling a streaming turn shall append a `turn_cancelled` event after any already-delivered native events, preserve the original cancellation signal, and avoid presenting a cancelled turn as a completed assistant response. A cancellation not handled by an interactive control surface shall terminate the CLI with exit code 130.
- **FR-28:** During an active `morphic chat` turn, Ctrl-C shall cancel only that turn, allow provider cleanup and durable cancellation recording to finish, rebuild the in-memory session from the ledger, and return to the prompt. Cancellation of the outer REPL task and Ctrl-C while no turn is active shall retain normal process-level cancellation behavior.
- **FR-29:** The CLI shall optionally expose an active chat turn through an authenticated, session-scoped loopback control transport. It shall bind only to `127.0.0.1`, use a random token stored in a mode-0600 descriptor, reject token/session/command mismatches, remove the descriptor after the turn, and remain disabled unless `morphic chat --control` is supplied. `morphic chat-control status/cancel` shall use this transport without directly exposing provider process details.
- **FR-30:** `morphic chat-control steer` shall accept one non-empty replacement prompt of at most 2048 UTF-8 bytes, reject later steer requests while cancellation cleanup is pending, cancel the current turn, replay the ledger, append a `turn_steered` audit event, and submit the replacement as a normal message in the same provider-bound native session and safety scope. A replacement beginning with `/` shall not be interpreted as a local slash command.

## Non-Functional Requirements

- **NFR-1 (Local-first):** The default path must work with Ollama for planning/draft behavior when configured API providers are unavailable or budget is exhausted.
- **NFR-2 (KV-cache safety):** System prompt prefixes must be stable. Dynamic timestamps, session IDs, file hashes, and user-specific values belong in user/context messages or event payloads, not the reusable system prefix.
- **NFR-3 (Append-only):** Session ledgers and memory updates must be append-only. Do not rewrite prior session turns.
- **NFR-4 (Latency):** The MVP REPL should produce visible progress within 500 ms after a user submits a turn, even if the full council deliberation takes longer.
- **NFR-5 (Observability):** Every engine choice, council decision, approval, tool call, command result, and verification step must be traceable to a session event.
- **NFR-6 (Safety):** Secret paths such as `~/.ssh`, `~/.aws`, `.env`, and credential files are CRITICAL risk unless explicitly classified otherwise by LAEE policy.
- **NFR-7 (Testability):** Unit tests use fake engines, fake tool executors, and fake session stores. No unit test may call a real LLM or external CLI.
- **NFR-8 (Compatibility):** The initial implementation must not break existing API task execution or existing `council-pilot` tests.

## Success Metrics

| Metric | Target |
|---|---|
| `morphic chat` can complete a read-only planning session | yes |
| Session events persisted in `.morphic/sessions/*.jsonl` | 100% of chat turns |
| Slash commands implemented in MVP | at least 6 |
| Unit tests for session store, context discovery, command parsing, approval flow | at least 20 |
| Framework imports in new domain files | 0 |
| Existing unit suite regression | 0 failures |
| User-visible first progress after submit | <= 500 ms in local dev |
| Direct-route engine calls per turn | exactly 1 |
| Direct-route failures hidden by local fallback | 0 |

## Relationship to Existing Specs

- `specs/council-pilot/` remains the low-level spike for two-engine debate during routing.
- `morphic-chat-cli` consumes that direction but is broader: terminal UX, session ledger, context/memory normalization, slash commands, approvals, and user-in-the-loop deliberation.
- `docs/AGENT_CLI.md` remains the engine landscape and routing reference.
- `docs/SEMANTIC_MEMORY.md` remains the memory architecture reference.

## Constitution Compliance

- [x] `domain/` has zero framework deps.
- [x] KV-cache safety declared.
- [x] LAEE risk classification declared.
- [x] Unit + integration test strategy defined.
- [x] Ollama path included.
