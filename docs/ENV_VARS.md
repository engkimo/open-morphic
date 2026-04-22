# Environment Variables

```env
# ── LLM APIs (すべてオプション、Ollamaだけでも動作する) ──
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GOOGLE_GEMINI_API_KEY=

# ── ローカルLLM (Ollama) ──
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_DEFAULT_MODEL=qwen3:8b
OLLAMA_CODING_MODEL=qwen3-coder:30b
LOCAL_FIRST=true              # Ollamaが使えるなら最優先

# ── Agent CLI Orchestration (v0.3) ──
OPENHANDS_BASE_URL=http://localhost:3000
OPENHANDS_MODEL=claude-sonnet-4-6
CLAUDE_CODE_SDK_ENABLED=true
GEMINI_CLI_ENABLED=true
CODEX_CLI_ENABLED=true
AGENT_DEFAULT_ENGINE=claude_code

# ── Semantic Memory (v0.3) ──
SEMANTIC_MEMORY_BACKEND=mem0              # mem0 | qdrant | custom
MEM0_API_KEY=
MEMORY_TARGET_TOKENS=800                  # ContextZipper圧縮目標
MEMORY_RETENTION_THRESHOLD=0.3            # 忘却曲線閾値

# ── Database ──
DATABASE_URL=postgresql://morphic:morphic@localhost:5432/morphic
REDIS_URL=redis://localhost:6379
QDRANT_URL=http://localhost:6333

# ── Cost Control ──
DEFAULT_MONTHLY_BUDGET_USD=50
DEFAULT_TASK_BUDGET_USD=1.0
AUTO_DOWNGRADE_ON_BUDGET=true
CACHE_BREAKPOINTS_ENABLED=true

# ── LAEE (v0.4) ──
LAEE_ENABLED=true
LAEE_APPROVAL_MODE=confirm-destructive   # full-auto | confirm-destructive | confirm-all
LAEE_AUDIT_LOG_PATH=.morphic/audit_log.jsonl
LAEE_UNDO_ENABLED=true
LAEE_MAX_CONCURRENT_SHELLS=10
LAEE_BROWSER_HEADLESS=true
LAEE_GUI_ENABLED=true
LAEE_CRON_ENABLED=true

# ── Morphic Settings ──
MORPHIC_ENV=development
AUTO_TOOL_INSTALL=false       # true: 自動, false: 承認制
EVOLUTION_ENABLED=true
PLANNING_MODE=interactive     # interactive | auto | disabled
TASK_SANDBOX=docker
```
