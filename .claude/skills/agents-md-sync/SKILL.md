---
name: agents-md-sync
description: Keep CLAUDE.md (thin router) and AGENTS.md (telegraph-style) in sync. Detects drift in command lists, paths, and routing tables between the two root instruction files.
when_to_use: After editing CLAUDE.md, AGENTS.md, docs/*.md router targets, or adding/removing subagents/skills.
argument-hint: "[--check | --fix]"
allowed-tools:
  - Read
  - Edit
  - Grep
  - Glob
model: sonnet
---

# AGENTS.md ↔ CLAUDE.md Sync

You keep the two root instruction files coherent. CLAUDE.md is for Claude Code (prose + @imports). AGENTS.md is for Codex CLI / Gemini CLI (telegraph bullets).

## Input

`$ARGUMENTS`:
- `--check` (default): report drift, don't modify.
- `--fix`: apply small mechanical fixes.

## What to sync

| Section | CLAUDE.md | AGENTS.md |
|---|---|---|
| Quick start commands | Quick Start block | Commands block |
| Docs index | Where to Look table | Repo Map block |
| Subagent roster | Custom Agents table | Agent CLI Routing |
| Skill roster | Custom Skills table | (skipped — Claude Code only) |
| Version | header `Version: X.Y.Z` | header `Version: X.Y.Z` |
| Last updated | header date | header date |

## Procedure

1. Parse CLAUDE.md and AGENTS.md.
2. Cross-check:
   - Version + date match.
   - Every `docs/*.md` referenced by CLAUDE.md exists.
   - Every subagent in `.claude/agents/` appears in CLAUDE.md's agents table.
   - Every skill in `.claude/skills/` appears in CLAUDE.md's skills table.
   - `morphic` commands in Quick Start match AGENTS.md Commands.
3. Report drift.
4. If `--fix`:
   - Add missing agent/skill rows (with placeholder role — user fills description).
   - Bump version+date when either file changed.
   - Never delete entries; flag for user.

## Output

```
# Sync Report — <date>

## Drift detected (N)
- Version mismatch: CLAUDE.md 0.5.2, AGENTS.md 0.5.1
- .claude/agents/new-agent.md not in CLAUDE.md roster
- docs/UCL.md referenced by AGENTS.md but missing

## Applied (if --fix)
- Bumped AGENTS.md to 0.5.2
- Added new-agent to CLAUDE.md table

## Manual action needed
- Fill description for new-agent
- Create docs/UCL.md or remove reference
```

## Guardrails

- **Never silently delete.** Missing entries = flag for user.
- Don't touch non-sync sections (Rules, Architecture, Safety summary).
- Abort if either file is >40 KB (exceeds Claude Code performance threshold).
