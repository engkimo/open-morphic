# Tech Stack

| カテゴリ | 技術 | 選定理由 |
|---|---|---|
| エージェント基盤 | **LangGraph** | DAG・状態管理・並列実行 |
| LLM統合 | **LiteLLM** | Ollama含む100+モデル統一API |
| ローカルLLM | **Ollama** | vibe-local実績、$0運用の鍵 |
| 構造化出力 | **Instructor** | Pydantic 型安全 |
| ベクトルDB | **Qdrant** | 意味検索・長期記憶 |
| 意味的記憶 | **mem0** | L2 Semantic Cache、自動抽出 |
| タスクキュー | **Redis + Celery** | 非同期・並列実行 |
| DB | **PostgreSQL + pgvector** | 実行履歴・ベクトル検索 |
| API | **FastAPI** | WebSocket対応 |
| フロント | **Next.js 15** | App Router |
| グラフUI | **React Flow** | タスクグラフビジュアライザー |
| UIコンポーネント | **Shadcn/ui** | シックなデザイン |
| MCP | **Model Context Protocol** | ツール統合標準 |
| A2A | **Google A2A Protocol** | エージェント間通信 |
| Agent CLI #1 | **OpenHands SDK** | Docker沙箱・SWE-bench 72% |
| Agent CLI #2 | **Claude Code SDK** | headless・PTC・Anthropic最高品質 |
| Agent CLI #3 | **Gemini CLI + ADK** | 2Mトークン・Seq/Par/Loop agents |
| Agent CLI #4 | **OpenAI Codex CLI** | Rust製・MCP server mode |
| 知識グラフ | **Neo4j / NetworkX** | L3 エンティティ・関係DB |
| ローカル実行 | **LAEE** | シェル・FS・ブラウザ・GUI・cron を統合制御 |
| ブラウザ自動化 | **Playwright** | Chromium/Firefox/WebKit、headless対応 |
| GUI自動化 | **AppleScript / osascript** | macOSネイティブ。Linux: xdotool |
| ファイル監視 | **watchdog** | クロスプラットフォーム inotify/FSEvents |
| スケジューラ | **APScheduler** | cron式定期実行 + ワンショット |

## Dev Commands

```bash
# Tests
uv run --extra dev pytest tests/unit/ -v
uv run --extra dev pytest tests/integration/ -v

# Lint
uv run --extra dev ruff check .

# Server
uv run uvicorn interface.api.main:app --host 0.0.0.0 --port 8001 --reload

# Health check
morphic doctor check
```

## Execution Priority Chain

```
Engine routing → ReactExecutor fallback → Direct LLM fallback
```

- **Fractal bypass**: LLM intent analysis → SIMPLE tasks skip fractal planning (TD-167)
- **Gate 2 skip**: Successful terminal nodes skip result evaluation LLM call (TD-168)
- **Parallel nodes**: Independent nodes execute via `asyncio.gather` (TD-169)
- **Persistence**: PG (primary), SQLite (fallback), InMemory (default)
