# AI Agent CLI Orchestration (v0.3)

> 「どのLLMモデルか」だけでなく「**どのエージェントランタイムか**」を選ぶ時代。
> Morphic-Agent は各CLIエージェントを**専門実行エンジン**として統合するメタオーケストレーターになる。

## なぜこれが重要か

従来のマルチLLMルーターは「モデルを選ぶ」だけだった。しかし2025-2026年には、各AIプロバイダーが独自のエージェント実行環境を持ち、それぞれが異なる強みを持つ「実行エンジン」として成熟した。

```
問題: Claude.ai / ChatGPT / Cursor / Gemini — コンテキストが断絶
      毎回コピペ、再説明のコストが膨大

解決: Morphic-Agent が全エージェントの「記憶のハブ」兼「指揮官」になる
      どのエンジンで実行しても、同じコンテキストを持つ状態を実現
```

## 各Agent CLIの特性分析

| エンジン | 強み | 弱み | 最適タスク |
|---|---|---|---|
| **OpenHands** | Docker沙箱, SWE-bench 72%, multi-agent delegation | セットアップ重い | 長時間ソフトウェア開発 |
| **Claude Code SDK** | Anthropic最高品質推論, headless API, PTC並列 | API課金 | アーキテクチャ設計・複雑推論 |
| **Gemini CLI + ADK** | 2Mトークン長文脈, Sequential/Parallel/Loop agents | Google依存 | ドキュメント分析・最新情報 |
| **OpenAI Codex CLI** | Rust製高速, MCP serverモード, AGENTS.md | ChatGPT依存 | 高速コード生成・CI/CDワーカー |
| **Ollama (local)** | $0運用, プライバシー完全保護 | 品質・速度の限界 | 反復タスク・ドラフト生成 |

---

## OpenHands 統合

```python
# OpenHands: Docker沙箱で長時間自律実行
# SWE-bench 72% (Claude Sonnet 4.5使用)
# AgentDelegateActionで子エージェントに委任可能

class OpenHandsDriver:
    """
    OpenHands SDK/REST API ラッパー
    - 沙箱Docker環境でコード実行
    - AgentDelegateAction でサブエージェント委任
    - REST + WebSocket でリアルタイム監視
    """
    def __init__(self):
        self.base_url = "http://localhost:3000"  # OpenHands local

    async def run_task(
        self,
        task: str,
        model: str = "claude-sonnet-4-6",
        max_iterations: int = 50,
        sandbox: bool = True
    ) -> TaskResult:
        session = await self.create_session(model=model)
        async for event in self.stream_events(session.id, task):
            if event.type == "agent_message":
                yield AgentProgress(message=event.content)
            elif event.type == "action":
                yield ActionEvent(tool=event.tool, args=event.args)
            elif event.type == "observation":
                yield ObservationEvent(result=event.result)
            elif event.type == "finish":
                return TaskResult(success=event.success, artifacts=event.artifacts)

    async def delegate_to_specialist(self, subtask: str, specialist_agent: str = "CodeAct"):
        """AgentDelegateAction: 専門エージェントに委任"""
        return await self.send_delegate_action(subtask, specialist_agent)


# セットアップ
# docker run -it --rm -p 3000:3000 \
#   -e LLM_API_KEY=$ANTHROPIC_API_KEY \
#   -e LLM_MODEL="claude-sonnet-4-6" \
#   ghcr.io/all-hands-ai/openhands:latest
```

**OpenHands V0 → V1 アーキテクチャ進化の4原則:**
1. **Stateless + Event-Sourced**: 状態はイベントログで復元可能
2. **Opt-in Sandboxing**: ローカル実行とDockerを選択的に使い分け
3. **Immutable Config**: セッション開始後に設定変更しない
4. **Composable SDK**: agent/tools/workspace/serverを分離したパッケージ構成

→ Morphic-Agentへの適用: event-sourceアーキテクチャを参考にAgentStateを設計

---

## Claude Code SDK 統合

```python
# Claude Code: Anthropic本命エージェントエンジン
# headlessモードで完全プログラマブル制御
# Programmatic Tool Calling (PTC) で並列ツール実行

class ClaudeCodeDriver:
    async def run_headless(
        self,
        prompt: str,
        session_id: str = None,
        allowed_tools: list[str] = None,
        output_format: str = "json"
    ) -> ClaudeCodeResult:
        cmd = ["claude", "-p", prompt, f"--output-format={output_format}"]
        if session_id:
            cmd += ["--session-id", session_id]
        if allowed_tools:
            cmd += ["--allowedTools", ",".join(allowed_tools)]
        result = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE)
        stdout, _ = await result.communicate()
        return ClaudeCodeResult.from_json(stdout)

    async def run_parallel_workers(self, tasks: list[dict]) -> list[ClaudeCodeResult]:
        """複数 Claude Code インスタンスを並列起動"""
        coroutines = [
            self.run_headless(
                prompt=task["prompt"],
                session_id=f"worker-{i}",
                allowed_tools=task.get("tools", ["Bash", "Read", "Write"])
            )
            for i, task in enumerate(tasks)
        ]
        return await asyncio.gather(*coroutines)
```

### Programmatic Tool Calling (PTC)
```python
# PTC: Claudeがコードを書いてツールを並列オーケストレーション
# 通常の tool_use: 1ツール呼び出し = 1 API往復 × N回
# PTC: Claude が code_execution で Python を書き、内部で 50 ツール並列呼び出し → 結果だけをコンテキストに返す

response = client.beta.messages.create(
    model="claude-sonnet-4-6",
    betas=["advanced-tool-use-2025-11-20"],
    max_tokens=4096,
    messages=[{"role": "user", "content": "50サーバーの死活監視を実行"}],
    tools=[
        {"type": "code_execution_20250825", "name": "code_execution"},
        {"type": "function", "name": "check_server_status", ...}
    ]
)
# → Claude が asyncio.gather で 50 並列実行する Python を書く
# → コンテキストには最終サマリーのみ (50ツール分の中間データなし)
# → KVキャッシュへの影響を最小化
```

---

## Gemini CLI + ADK 統合

```python
# Gemini CLI: 2Mトークン長文脈 + Grounding (最新情報)
# Google ADK: Sequential/Parallel/Loop agents + Vertex AI

class GeminiCLIDriver:
    async def analyze_large_context(self, content: str, query: str, use_grounding: bool = False) -> str:
        """Gemini の 2M トークン窓を活用した大規模コンテキスト分析"""
        cmd = ["gemini", "-p", f"{query}\n\nContext:\n{content}"]
        if use_grounding:
            cmd += ["--grounding"]
        result = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE)
        stdout, _ = await result.communicate()
        return stdout.decode()

    def build_adk_workflow(self) -> SequentialAgent:
        parallel_fetcher = ParallelAgent(
            name="info_fetcher",
            agents=[
                LlmAgent(name="flight_agent", model="gemini-2.5-flash"),
                LlmAgent(name="hotel_agent", model="gemini-2.5-flash"),
            ]
        )
        return SequentialAgent(
            name="travel_planner",
            agents=[
                LlmAgent(name="sightseeing_agent", ...),
                parallel_fetcher,
                LlmAgent(name="summary_agent", ...),
                LlmAgent(name="reviewer_agent", ...),
            ]
        )
```

### ADKの重要設計パターン
```
SequentialAgent  → 決定論的パイプライン (出力が予測可能)
ParallelAgent    → 独立タスクの同時実行 (Cursor 原則と一致)
LoopAgent        → 品質基準を満たすまで反復 (自己改善ループ)
LlmAgent.transfer → 動的ルーティング (次のエージェントを LLM が判断)

⚠️ 落とし穴: 単純に LlmAgent をネストすると「良き受付係、悪きPM」問題
→ 最初のサブエージェントに制御が移ったら、親エージェントは文脈を失う
→ SequentialAgent で明示的に制御フローを設計することが重要
```

---

## OpenAI Codex CLI 統合

```python
# OpenAI Codex CLI: Rust製オープンソース
# MCP serverモードで「別エージェントのツール」として使える
# AGENTS.md でリポジトリ固有コンテキストを注入

class CodexCLIDriver:
    async def run_exec(
        self,
        prompt: str,
        approval_mode: str = "on-request",  # never | on-request | full-auto
        model: str = "gpt-5-codex",
        use_oss: bool = False
    ) -> CodexResult:
        cmd = ["codex", "exec", prompt,
               f"--approval-mode={approval_mode}",
               f"--model={model}"]
        if use_oss:
            cmd += ["--oss"]  # Ollama 互換ローカルモデルへ
        result = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE)
        stdout, _ = await result.communicate()
        return CodexResult.parse(stdout)

    async def start_as_mcp_server(self) -> subprocess.Popen:
        """Codex を MCP サーバーとして起動"""
        return subprocess.Popen(["codex", "mcp", "stdio"],
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE)
```

`AGENTS.md` はリポジトリ固有の永続コンテキスト。`~/.codex/config.toml` や `AGENTS.md` に書くと、Codex が起動時に自動でプロジェクト知識を読み込む。Morphic-Agent の `CLAUDE.md` と同様の役割。

---

## Agent CLI Router

```python
class AgentCLIRouter:
    AGENT_ROUTING_MAP = {
        "long_running_dev":    "openhands",   # SWE-bench 72%, Docker 沙箱
        "complex_reasoning":   "claude_code", # Anthropic 最高品質
        "long_context":        "gemini_cli",  # 2M トークン, Grounding
        "fast_code_gen":       "codex_cli",   # Rust 製高速, MCP server
        "cost_zero":           "ollama",      # ローカル無料
        "workflow_pipeline":   "adk",         # Sequential / Parallel / Loop
    }

    async def route(self, task: Task) -> AgentEngine:
        task_type = await self.classify_task(task)
        if self.budget_exhausted():
            return self.engines["ollama"]
        engine_name = self.AGENT_ROUTING_MAP.get(task_type, "claude_code")
        engine = self.engines[engine_name]
        if not await engine.is_available():
            engine = self.fallback_engine(engine_name)
        return engine

    def classify_task(self, task: Task) -> str:
        if task.estimated_hours > 1:       return "long_running_dev"
        if task.context_tokens > 100_000:  return "long_context"
        if task.requires_ci_cd:            return "fast_code_gen"
        if task.budget == 0:               return "cost_zero"
        if len(task.pipeline_steps) > 3:   return "workflow_pipeline"
        return "complex_reasoning"


class AgentEngine(Protocol):
    async def is_available(self) -> bool: ...
    async def run(self, task: Task) -> TaskResult: ...
    async def get_cost_estimate(self, task: Task) -> float: ...
    def get_capabilities(self) -> list[str]: ...
```

**全体像:**
```
[Morphic-Agent Orchestrator]
         │
         ├── 長時間開発タスク ────→ [OpenHands] (Docker沙箱, 自律実行)
         ├── 設計・レビュー ─────→ [Claude Code SDK] (headless並列, PTC)
         ├── 長文脈分析 ─────────→ [Gemini CLI + ADK] (2M tokens, Grounding)
         ├── 高速生成・CI/CD ────→ [Codex CLI] (MCP server, exec)
         ├── コスト $0 タスク ───→ [Ollama] (ローカル完全無料)
         │
         └── [Shared Semantic Memory] ← 全エンジン共通の記憶ハブ
```
