# Agent CLI Operational Spec Catalog

> Reference catalog for the operational features Morphic Chat CLI should support. This is a clean-room catalog of expected capabilities, not an implementation import from any third-party project.

## Positioning

Modern agentic coding CLIs are not just model wrappers. They are local development harnesses with chat UX, tool execution, permissions, session state, project memory, diagnostics, hooks, and automation surfaces.

Morphic should satisfy that baseline while adding its own differentiator:

```
Baseline:
  high-quality terminal agent CLI operations

Morphic extension:
  multi-engine council orchestration and canonical workspace metadata
```

## 1. Terminal UX

Required:
- Interactive REPL.
- Streaming assistant output.
- Visible tool activity.
- Interrupt and continue.
- Diff preview before edits.
- Approval prompts.
- Resume latest session.
- Compact status line: session id, mode, active goal, active engine/role, permission mode.

MVP:
- Line-oriented REPL using Rich/Typer or existing CLI stack.
- Plain progress events instead of full-screen TUI.

Later:
- Textual full-screen layout with chat pane, council pane, tool log, diff viewer, and approval panel.

## 2. Slash Commands

Required command categories:
- `/help`: list commands.
- `/status`: current goal, session id, permission mode, active roles, pending approvals.
- `/doctor`: environment and engine availability checks.
- `/context`: discovered instruction sources and precedence.
- `/memory`: active memory entries and pending memory writes.
- `/engines`: registered engines, availability, cost profile, capability profile.
- `/council`: role assignments, last deliberation, leader decision.
- `/tools`: tool registry and recent tool calls.
- `/diff`: current proposed/working diff summary.
- `/approvals`: pending and resolved approvals.
- `/resume`: resume another session.
- `/export`: export metadata projections.
- `/quit`: close session with summary.

MVP command subset:
- `/help`
- `/status`
- `/doctor`
- `/context`
- `/engines`
- `/diff`
- `/quit`

## 3. Session Ledger

Canonical path:

```
.morphic/sessions/<session_id>.jsonl
```

Properties:
- Append-only.
- One JSON object per event.
- Stable event schema.
- Session can be reconstructed from events.
- User-visible transcript can be derived from the ledger.
- Tool/action/audit details can be filtered separately from chat messages.

Minimum event types:
- `session_started`
- `user_message`
- `assistant_message`
- `context_indexed`
- `council_event`
- `tool_call_requested`
- `approval_requested`
- `approval_resolved`
- `tool_call_completed`
- `diff_proposed`
- `verification_result`
- `session_summary`

## 4. Context and Memory

Discovery sources:
- `AGENTS.md`
- `CLAUDE.md`
- `.claude/agents/`
- `.claude/skills/`
- `.claude/commands/`
- `.claude/rules/`
- `GEMINI.md`
- `.cursor/rules/`
- `.github/copilot-instructions.md`
- `.morphic/context/`
- `.morphic/memory/`
- `docs/` entries referenced by thin routers

Canonical index:

```
.morphic/context/index.json
```

Index fields:
- `source_path`
- `source_type`
- `scope`
- `precedence`
- `content_hash`
- `imported_at`
- `sections`
- `warnings`

Rules:
- Discovery is read-only.
- Sync/export is explicit.
- `.morphic` should become canonical over time.
- Existing tool-specific metadata is never overwritten silently.

## 5. Tool System

Required tool categories:
- File read.
- File search.
- File edit.
- Shell command.
- Git status/diff.
- Test command.
- Lint command.
- Context discovery.
- Memory write.
- Engine invocation.

Tool result normalization:
- `tool_name`
- `arguments`
- `risk_level`
- `approval_id`
- `started_at`
- `completed_at`
- `exit_code`
- `stdout_summary`
- `stderr_summary`
- `artifacts`

## 6. Permission and Safety

Permission modes:
- `read-only`: no workspace mutation.
- `workspace-write`: can edit workspace files, cannot run destructive shell/git commands without approval.
- `confirm-destructive`: default for local development; destructive actions require confirmation.
- `danger-full-access`: explicit opt-in only.

Risk levels:
- `safe`
- `low`
- `medium`
- `high`
- `critical`

Critical examples:
- Secret paths: `~/.ssh`, `~/.aws`, `.env`.
- Credential exfiltration.
- Deleting broad file trees.
- Pushing to protected branches.
- Running untrusted remote scripts.

## 7. Hooks and Harness

Hook types:
- `pre_tool`
- `post_tool`
- `pre_edit`
- `post_edit`
- `pre_shell`
- `post_shell`
- `pre_commit`
- `session_end`

Requirements:
- Hook validation must be available through `/doctor`.
- Invalid hooks should be isolated and reported; they should not disable unrelated valid hooks.
- Hook execution results should be session events.
- Harness policy should live in `.morphic/hooks/` first, with exports to tool-specific formats later.

## 8. Config

Recommended precedence:
1. Built-in defaults.
2. User config: `~/.config/morphic/settings.json`.
3. Project config: `.morphic/settings.json`.
4. Local project override: `.morphic/settings.local.json`.
5. Environment variables.
6. Explicit CLI flags.

Config domains:
- Default engine routing.
- Permission mode.
- Model/provider credentials by reference only.
- Session retention.
- Hook enablement.
- Output format.
- Cost limits.
- Context discovery includes/excludes.

## 9. Engine and Provider Registry

Engine profile fields:
- `id`
- `display_name`
- `kind`: external CLI, SDK, direct API, local model, sandbox runtime.
- `capabilities`
- `cost_profile`
- `latency_profile`
- `context_window`
- `availability_check`
- `supports_streaming`
- `supports_editing`
- `supports_sandbox`
- `supports_json_output`

Initial engines:
- `ollama`
- `direct_llm`
- `codex_cli`
- `claude_code`
- `gemini_cli`
- `openhands`

## 10. Diagnostics and Automation

Diagnostics:
- `morphic doctor agents`
- `morphic doctor context`
- `morphic doctor hooks`
- `morphic doctor engines`
- `morphic chat --doctor --json`

Automation:
- Non-interactive `morphic code "<goal>"`.
- JSON event stream option.
- Stable exit codes.
- CI-friendly output.
- Machine-readable status and doctor results.

## 11. Morphic-Specific Council Runtime

Roles:
- `planner`: decomposes the task and proposes approach.
- `architect`: checks architecture and boundaries.
- `implementer`: proposes edits and implementation sequence.
- `critic`: finds risks, missing tests, and weak assumptions.
- `tester`: selects verification commands and interprets failures.
- `leader`: selects the next action and final answer.
- `reflector`: decides whether the goal is genuinely satisfied.

Selection principle:
- Evidence beats votes.
- A plan wins because it satisfies constraints and verification, not because more engines preferred it.

Evidence dimensions:
- Repo rules.
- Clean Architecture compliance.
- Test coverage.
- Minimal change size.
- Security risk.
- Cost.
- Latency.
- User constraints.
- Previous session memory.
- Actual command results.

