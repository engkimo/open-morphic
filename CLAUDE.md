# Morphic-Agent — Self-Evolving AI Agent Framework
> "ユーザーの意図を汲み取り、タスクをこなし、失敗を糧に自己進化する"
> *Mission Control for Intelligence*

---

## 🧠 Project Vision

**Morphic-Agent** は、単体のアルゴリズムでは解決できない複雑なタスクを、複数のAI・ツール・エージェントを動的に組み合わせることで解決し、**実行履歴・失敗・フィードバックから自己進化し続けるAIエージェントフレームワーク**である。

**競合との差別化:**
- **Manus超え**: タスクグラフ可視化 + ユーザーによるノード単位コスト制御 + 文脈工学5原則を初期から実装
- **Devin超え**: Interactive Planning + ローカルLLM対応でコスト$0運用可能
- **Windsurf超え**: クロスプラットフォームコンテキストブリッジで複数AIアプリの断絶解消
- **OpenClaw超え**: 自律ツール発見・マーケットプレイス登録・他エージェントとの共有 + **ローカルPC直接制御（LAEE）でユーザーのマシンを「手足」にする**
- **v0.3新軸: メタオーケストレーター**: OpenHands / Claude Code / Gemini CLI / Codex CLIを「専門実行エンジン」として統合管理 + Semantic Fingerprintで全AIの記憶を統一
- **v0.4新軸: Local Autonomous Execution Engine (LAEE)**: ユーザーのローカルPCを直接操作。シェル・ファイル・ブラウザ・GUI・開発ツールをエージェントが自律制御。3段階承認モードでユーザー自己責任のもと full-auto 運用可能
- **v0.5新軸: Unified Cognitive Layer (UCL)**: 全エージェントの記憶・タスク状態・判断を統合する共有認知層。タスクをAgent AからAgent Bへ完全引き継ぎ。個々のAIは「脳の領域」、UCLは「記憶と意識の統合」。他フレームワークにない独自性

---

## 🏗️ Architecture Overview (v0.5)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                               Morphic-Agent CORE                                     │
│                                                                              │
│  [User Intent Input]                                                         │
│        │                                                                     │
│        ▼                                                                     │
│  ┌─────────────┐    ┌─────────────────────────────────────────────────────┐ │
│  │ Intent      │    │            Task Graph Engine (DAG)                  │ │
│  │ Analyzer    │──▶ │  Goal ──▶ SubTask A ──▶ SubTask A1                 │ │
│  │ (LLM Layer) │    │       ├──▶ SubTask B ──▶ SubTask B1                │ │
│  └─────────────┘    │       └──[失敗] Fallback ──▶ SubTask C            │ │
│                     └─────────────────────────────────────────────────────┘ │
│                                    │                                        │
│                    ┌───────────────┴────────────────┐                       │
│                    ▼                                ▼                        │
│  ┌─────────────────────────────┐   ┌──────────────────────────────────────┐ │
│  │  Agent CLI Orchestration    │   │     Multi-LLM Execution Engine       │ │
│  │  (v0.3 NEW)                 │   │                                      │ │
│  │  ┌──────────┐ ┌──────────┐  │   │  ┌──────┐ ┌──────┐ ┌──────┐ ┌────┐ │ │
│  │  │OpenHands │ │ Claude   │  │   │  │Claude│ │GPT-4o│ │Gemini│ │OLL │ │ │
│  │  │(Docker   │ │ Code SDK │  │   │  │      │ │      │ │      │ │AMA │ │ │
│  │  │ sandbox) │ │(headless)│  │   │  │推論  │ │マルチ│ │長文  │ │FREE│ │ │
│  │  └──────────┘ └──────────┘  │   │  └──────┘ └──────┘ └──────┘ └────┘ │ │
│  │  ┌──────────┐ ┌──────────┐  │   └──────────────────────────────────────┘ │
│  │  │ Gemini   │ │ Codex    │  │                                            │
│  │  │ CLI+ADK  │ │ CLI MCP  │  │                                            │
│  │  │(2M ctx)  │ │(Rust製)  │  │                                            │
│  │  └──────────┘ └──────────┘  │                                            │
│  └─────────────────────────────┘                                            │
│                                    │                                        │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │  Local Autonomous Execution Engine (LAEE) — v0.4 NEW                  │ │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐  │ │
│  │  │shell_* │ │ fs_*   │ │browser*│ │system_*│ │ dev_*  │ │ gui_*  │  │ │
│  │  │bash/zsh│ │CRUD    │ │Playwrt │ │process │ │git/dock│ │macOS   │  │ │
│  │  │async   │ │search  │ │scrape  │ │service │ │pkg mgr │ │a11y/ocr│  │ │
│  │  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘ └────────┘  │ │
│  │  [Safety: full-auto | confirm-destructive | confirm-all] + AuditLog  │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                    │                                        │
│  ┌────────────────┐  ┌──────────────┐  ┌──────────────────────────────────┐ │
│  │ Semantic       │  │   Skill /    │  │   Self-Evolution Engine          │ │
│  │ Memory Layer   │  │  Marketplace │  │                                  │ │
│  │ (L1→L4 cache)  │  │              │  │                                  │ │
│  └────────────────┘  └──────────────┘  └──────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔑 Context Engineering — Manus が4回作り直して到達した鉄則

> Manusが「Stochastic Graduate Descent」と呼ぶ試行錯誤の結晶。
> Morphic-Agentはこれを**最初から**組み込むことで、同じ轍を踏まない。

### 原則 1: KV-Cache を設計の中心に置く

**なぜ重要か:** Claude Sonnetでは、キャッシュ済みトークンは $0.30/MTok、未キャッシュは $3/MTok（**10倍の差**）。エージェントのinput:output比は約100:1なので、キャッシュ設計だけでコストを劇的に削減できる。

```python
# ✅ 正しい設計: システムプロンプトの先頭を安定させる
SYSTEM_PROMPT_PREFIX = """
You are Morphic-Agent, a self-evolving AI agent...
[ここは絶対に変えない安定した記述]
"""
# 日時・セッション情報は末尾か動的セクションに置く

# ❌ NG パターン (毎回キャッシュ無効化)
# SYSTEM_PROMPT = f"Current time: {datetime.now().isoformat()}\n..."

# ✅ コンテキストはappend-only（過去を修正しない）
class AgentContext:
    def append_action(self, action): ...   # 追記のみ
    def append_observation(self, obs): ... # 追記のみ
    # serialize() は常に決定論的（JSON sort_keys=True）
```

**実装指針:**
- システムプロンプト先頭は不変（日時は末尾か動的セクション）
- JSON/XMLシリアライズは `sort_keys=True` で決定論的に
- キャッシュブレークポイントはシステムプロンプト末尾に手動設置
- セルフホスト（vLLM等）の場合はprefix cachingを有効化

---

### 原則 2: ツールは「マスク」する。削除しない

**なぜ重要か:** ツールを動的追加・削除するとKVキャッシュが無効化される。過去のアクションが未定義ツールを参照して混乱も生じる。

```python
class ToolStateMachine:
    """コンテキスト依存でツール使用可否を制御。定義は常に全量保持。"""
    def get_allowed_tools(self, state: AgentState) -> list[str]:
        all_tools = self.registry.get_all()  # 常に全ツール定義
        return [t for t in all_tools if self._is_allowed(t, state)]
```

**ツール命名規則（プレフィックスでグループ制御）:**
```
browser_*   ブラウザ操作
shell_*     シェル・ターミナル
file_*      ファイル操作
memory_*    記憶・コンテキスト
task_*      タスク管理 (task_create/list/get/update)
agent_*     エージェント間通信 (sub_agent/parallel_agents)
tool_*      ツール管理
```

---

### 原則 3: ファイルシステムを「無限のコンテキスト」として使う

```python
class FileSystemContext:
    """圧縮は「復元可能な形式」のみ許可。情報損失ゼロ。"""
    def compress_webpage(self, url: str, content: str) -> str:
        self.save(f"cache/{hash(url)}.txt", content)
        return f"[Cached at cache/{hash(url)}.txt, URL: {url}]"
    # URLが残れば再取得可能 → コンテキストからは省略OK
```

---

### 原則 4: `todo.md` でアテンションを操作する

LLMは文脈の先頭・末尾に最も注目する（中間希薄化）。現在のゴールと進捗を繰り返し「再引用」することで長タスクのドリフトを防ぐ。

```markdown
# todo.md — エージェントが各イテレーション先頭で読み、末尾で更新

## Goal: ユーザーの旅行プランを作成する

### Tasks
- [x] 目的地の候補を検索
- [x] ホテルを比較
- [ ] **[IN PROGRESS]** 最安値フライトを検索
- [ ] ルートプランを作成
- [ ] PDFレポート生成
```

---

### 原則 5: 観察の多様性を意図的に維持する

類似した観察が連続するとLLMがパターンを模倣してドリフトする。

```python
class ObservationSerializer:
    templates = [
        "Result: {result}\nStatus: {status}",
        "Observation #{n}: {result} [{status}]",
        "Completed: {result} | State: {status}",
    ]
    def serialize(self, obs, n: int) -> str:
        return self.templates[n % len(self.templates)].format(**obs, n=n)
```

---

## 🤖 AI Agent CLI Orchestration — v0.3の核心

> 「どのLLMモデルか」だけでなく「**どのエージェントランタイムか**」を選ぶ時代。
> Morphic-Agentは各CLIエージェントを**専門実行エンジン**として統合するメタオーケストレーターになる。

### なぜこれが重要か

従来のマルチLLMルーターは「モデルを選ぶ」だけだった。しかし2025年には、各AIプロバイダーが独自のエージェント実行環境を持ち、それぞれが異なる強みを持つ「実行エンジン」として成熟した。

```
問題: Claude.ai / ChatGPT / Cursor / Gemini — コンテキストが断絶
      毎回コピペ、再説明のコストが膨大

解決: Morphic-Agent が全エージェントの「記憶のハブ」兼「指揮官」になる
      どのエンジンで実行しても、同じコンテキストを持つ状態を実現
```

### 各Agent CLIの特性分析

| エンジン | 強み | 弱み | 最適タスク |
|---|---|---|---|
| **OpenHands** | Docker沙箱, SWE-bench 72%, multi-agent delegation | セットアップ重い | 長時間ソフトウェア開発タスク |
| **Claude Code SDK** | Anthropic最高品質推論, headless API, PTC並列 | API課金 | アーキテクチャ設計・複雑推論 |
| **Gemini CLI + ADK** | 2Mトークン長文脈, Sequential/Parallel/Loop agents | Google依存 | ドキュメント分析・最新情報 |
| **OpenAI Codex CLI** | Rust製高速, MCP serverモード, AGENTS.md | ChatGPT依存 | 高速コード生成・CI/CDワーカー |
| **Ollama (local)** | $0運用, プライバシー完全保護 | 品質・速度の限界 | 反復タスク・ドラフト生成 |

---

### OpenHands 統合

```python
# OpenHands: Docker沙箱で長時間自律実行
# SWE-bench 72%（Claude Sonnet 4.5使用）
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
        # または OpenHands Cloud: https://app.openhands.ai/api
    
    async def run_task(
        self,
        task: str,
        model: str = "claude-sonnet-4-6",   # モデル差し替え可能
        max_iterations: int = 50,
        sandbox: bool = True
    ) -> TaskResult:
        """
        長時間自律タスクをOpenHands沙箱で実行
        内部でfile_read/write/bash/browserをエージェントが自律使用
        """
        session = await self.create_session(model=model)
        
        # イベントストリームで進捗をリアルタイム受信
        async for event in self.stream_events(session.id, task):
            if event.type == "agent_message":
                yield AgentProgress(message=event.content)
            elif event.type == "action":
                yield ActionEvent(tool=event.tool, args=event.args)
            elif event.type == "observation":
                yield ObservationEvent(result=event.result)
            elif event.type == "finish":
                return TaskResult(
                    success=event.success,
                    artifacts=event.artifacts
                )
    
    async def delegate_to_specialist(
        self,
        subtask: str,
        specialist_agent: str = "CodeAct"
    ) -> SubResult:
        """AgentDelegateAction: 専門エージェントに委任"""
        # 例: CodeActAgent（コーディング）, BrowsingAgent（ウェブ）
        return await self.send_delegate_action(subtask, specialist_agent)


# セットアップ
# docker run -it --rm -p 3000:3000 \
#   -e LLM_API_KEY=$ANTHROPIC_API_KEY \
#   -e LLM_MODEL="claude-sonnet-4-6" \
#   ghcr.io/all-hands-ai/openhands:latest
```

**OpenHandsの設計原則（v1からの教訓）:**
```
V0 → V1 アーキテクチャ進化の4原則:
1. Stateless + Event-Sourced: 状態はイベントログで復元可能
2. Opt-in Sandboxing: ローカル実行とDockerを選択的に使い分け
3. Immutable Config: セッション開始後に設定変更しない
4. Composable SDK: agent/tools/workspace/serverを分離したパッケージ構成

→ Morphic-Agentへの適用: event-sourceアーキテクチャを参考にAgentStateを設計
```

---

### Claude Code SDK 統合

```python
# Claude Code: Anthropicの本命エージェントエンジン
# headlessモードで完全プログラマブル制御
# Programmatic Tool Calling (PTC) で並列ツール実行

import subprocess
import json
import asyncio
from claude_code_sdk import ClaudeCode  # Python SDK (2025/06 GA)

class ClaudeCodeDriver:
    """
    Claude Code SDK ラッパー
    - headless (-p) でCI/CDパイプラインから呼び出し
    - Python/TypeScript SDKで構造化出力
    - 複数インスタンスの並列起動（--session-id）
    - Programmatic Tool Calling (PTC) でコンテキスト節約
    """
    
    async def run_headless(
        self,
        prompt: str,
        session_id: str = None,
        allowed_tools: list[str] = None,
        output_format: str = "json"
    ) -> ClaudeCodeResult:
        """
        CLIヘッドレスモードで実行
        Cursor互換: --session-idで会話継続可能
        """
        cmd = ["claude", "-p", prompt, f"--output-format={output_format}"]
        
        if session_id:
            cmd += ["--session-id", session_id]
        
        if allowed_tools:
            # セキュリティ: 許可ツールを明示的に指定
            tools_str = ",".join(allowed_tools)
            cmd += ["--allowedTools", tools_str]
        
        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await result.communicate()
        return ClaudeCodeResult.from_json(stdout)
    
    async def run_parallel_workers(
        self,
        tasks: list[dict]
    ) -> list[ClaudeCodeResult]:
        """
        複数のClaude Codeインスタンスを並列起動
        例: セキュリティレビュー + テスト生成 + ドキュメント作成を同時実行
        """
        coroutines = [
            self.run_headless(
                prompt=task["prompt"],
                session_id=f"worker-{i}",
                allowed_tools=task.get("tools", ["Bash", "Read", "Write"])
            )
            for i, task in enumerate(tasks)
        ]
        # Cursor鉄則: DEFAULT TO PARALLEL
        return await asyncio.gather(*coroutines)
    
    async def run_with_sdk(
        self,
        prompt: str,
        thread_id: str = None
    ) -> str:
        """
        Python SDK使用: より細粒度な制御
        構造化出力・ツール承認コールバック・ネイティブメッセージオブジェクト
        """
        from anthropic_code_sdk import ClaudeCode as SDK
        client = SDK()
        thread = client.start_thread(thread_id=thread_id)
        return await thread.run(prompt)


# 使用例: 3つのClaude Codeワーカーを並列実行
# claude -p "src/auth/のセキュリティ問題を分析" --session-id "sec-review" &
# claude -p "src/api/のユニットテストを書く" --session-id "test-gen" &
# claude -p "src/db/のクエリ最適化" --session-id "db-opt" &
# wait
```

**Claude Code SDK の核心機能 - Programmatic Tool Calling (PTC):**
```python
# PTC: Claudeがコードを書いてツールを並列オーケストレーション
# 通常のtool_use: 1ツール呼び出し = 1 API往復 × N回
# PTC: Claudeがcode_executionでPythonスクリプトを書き、
#      そのスクリプト内で50ツールを並列呼び出し → 結果だけをコンテキストに返す

# API設定例
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
# → Claudeがasyncio.gatherで50並列実行するPythonを書く
# → コンテキストには最終サマリーのみ（50ツール分の中間データなし）
# → KVキャッシュへの影響を最小化（Manus原則との相乗効果）
```

---

### Gemini CLI + ADK 統合

```python
# Gemini CLI: 2Mトークン長文脈 + Grounding（最新情報）
# Google ADK: Sequential/Parallel/Loop agents + Vertex AI
# MCP native サポート（2025/05〜）

import subprocess
from google.adk.agents import LlmAgent, SequentialAgent, ParallelAgent

class GeminiCLIDriver:
    """
    Gemini CLI + ADK ラッパー
    - 2Mトークン: 大規模コードベース・ドキュメント一括分析
    - ADK Parallel/Sequential: 組み込みワークフロー型
    - Grounding: Google Search連動でリアルタイム情報
    - Vertex AI: エンタープライズ規模デプロイ
    """
    
    async def analyze_large_context(
        self,
        content: str,
        query: str,
        use_grounding: bool = False
    ) -> str:
        """
        Geminiの2Mトークン窓を活用した大規模コンテキスト分析
        他のモデルでは分割処理が必要な案件を一括処理
        """
        cmd = ["gemini", "-p", f"{query}\n\nContext:\n{content}"]
        if use_grounding:
            cmd += ["--grounding"]  # Google Search連動
        
        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE
        )
        stdout, _ = await result.communicate()
        return stdout.decode()
    
    def build_adk_workflow(self) -> SequentialAgent:
        """
        ADKのワークフロー型エージェント構築
        SequentialAgent: A→B→C の順次実行
        ParallelAgent: A+B+C の同時実行
        LoopAgent: 条件が満たされるまで繰り返し
        """
        # フライト + ホテル情報を並列取得
        parallel_fetcher = ParallelAgent(
            name="info_fetcher",
            agents=[
                LlmAgent(name="flight_agent", model="gemini-2.5-flash",
                         instruction="フライト情報を取得"),
                LlmAgent(name="hotel_agent", model="gemini-2.5-flash",
                         instruction="ホテル情報を取得"),
            ]
        )
        
        # 全体フローを順次実行
        return SequentialAgent(
            name="travel_planner",
            agents=[
                LlmAgent(name="sightseeing_agent", ...),
                parallel_fetcher,                         # 並列フェーズ
                LlmAgent(name="summary_agent", ...),
                LlmAgent(name="reviewer_agent", ...),     # 自己レビュー
            ]
        )


# ADK AGENTS.md相当: llms-full.txt
# ADKリポジトリのllms-full.txtをGemini CLIに渡すと
# ADKの全APIを理解した専門家として振る舞う（50%トークン削減）
# → Morphic-Agentでは各フレームワークの"知識ファイル"をRAGで管理する
```

**ADKの重要設計パターン:**
```
ADKワークフロー vs LLMドリブン の使い分け:

SequentialAgent  → 決定論的パイプライン（出力が予測可能な場合）
ParallelAgent    → 独立タスクの同時実行（Cursor原則と一致）
LoopAgent        → 品質基準を満たすまで反復（自己改善ループ）
LlmAgent.transfer → 動的ルーティング（次のエージェントをLLMが判断）

⚠️ 落とし穴: 単純にLlmAgentをネストすると「良き受付係、悪きPM」問題
→ 最初のサブエージェントに制御が移ったら、親エージェントは文脈を失う
→ SequentialAgentで明示的に制御フローを設計することが重要
```

---

### OpenAI Codex CLI 統合

```python
# OpenAI Codex CLI: Rust製オープンソース
# MCP serverモードで「別エージェントのツール」として使える
# AGENTS.md でリポジトリ固有コンテキストを注入
# codex exec で非インタラクティブ自動化
# @openai/codex-sdk (TypeScript) でプログラマブル制御

import subprocess
import json

class CodexCLIDriver:
    """
    OpenAI Codex CLI ラッパー
    - exec: ヘッドレス非インタラクティブ実行
    - mcp: MCP serverとして起動 → Morphic-Agentのツールとして使える
    - multi-agent: 並列ワーカー（experimental）
    - AGENTS.md: リポジトリコンテキスト自動注入
    """
    
    async def run_exec(
        self,
        prompt: str,
        approval_mode: str = "on-request",  # never | on-request | full-auto
        model: str = "gpt-5-codex",
        use_oss: bool = False               # Ollama互換ローカルモデル
    ) -> CodexResult:
        """
        headless実行 (codex exec)
        CI/CDパイプライン・自動化ワークフロー向け
        """
        cmd = ["codex", "exec", prompt,
               f"--approval-mode={approval_mode}",
               f"--model={model}"]
        
        if use_oss:
            cmd += ["--oss"]  # OllamaローカルモデルにRouting
        
        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            cwd=self.workspace_dir
        )
        stdout, _ = await result.communicate()
        return CodexResult.parse(stdout)
    
    async def start_as_mcp_server(self) -> subprocess.Popen:
        """
        CodexをMCPサーバーとして起動
        → Morphic-Agentや他のエージェントが「codex_execute」ツールとして呼び出せる
        
        codex mcp stdio
        """
        return subprocess.Popen(
            ["codex", "mcp", "stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
    
    async def run_parallel_workers(
        self,
        tasks: list[str],
        roles: dict = None
    ) -> list[CodexResult]:
        """
        マルチエージェント並列実行 (experimental)
        config.tomlでroleを定義して分業
        
        [agents]
        roles = ["reviewer", "frontend", "backend", "tester"]
        """
        return await asyncio.gather(*[
            self.run_exec(task, approval_mode="never")
            for task in tasks
        ])


# TypeScript SDK使用例
# import { Codex } from "@openai/codex-sdk";
# const codex = new Codex();
# const thread = codex.startThread();
# const result = await thread.run("CI失敗の診断と修正プランを作成");
# // 同じスレッドで継続
# const result2 = await thread.run("↑の修正を実際に適用して");


# AGENTS.md: リポジトリ固有の永続コンテキスト
# ~/.codex/config.toml や AGENTS.md に書くことで
# Codexが起動時に自動でプロジェクト知識を読み込む
# → Morphic-Agentのmorphic_agent_rules.md と同様の役割
```

---

### Agent CLI ルーターの設計

```python
class AgentCLIRouter:
    """
    「どのLLMモデルか」に加えて「どのエージェントランタイムか」を選ぶ
    タスク特性 × コスト × 利用可能性 で最適エンジンを選択
    """
    
    # タスク特性 → 最適エンジンのマッピング
    AGENT_ROUTING_MAP = {
        # 長時間・自律的ソフトウェア開発
        "long_running_dev":    "openhands",   # SWE-bench 72%, Docker沙箱
        
        # アーキテクチャ設計・複雑な推論・コードレビュー
        "complex_reasoning":   "claude_code", # Anthropic最高品質
        
        # 大規模ドキュメント分析・長文脈タスク
        "long_context":        "gemini_cli",  # 2Mトークン, Grounding
        
        # 高速コード生成・CI/CDワーカー・並列タスク
        "fast_code_gen":       "codex_cli",   # Rust製高速, MCP server mode
        
        # $0必須・プライバシー要件・反復タスク
        "cost_zero":           "ollama",      # ローカル無料
        
        # 複数工程のワークフロー（Seq/Par/Loop）
        "workflow_pipeline":   "adk",         # Google ADK ワークフロー型
    }
    
    async def route(self, task: Task) -> AgentEngine:
        task_type = await self.classify_task(task)
        
        # コスト制約チェック
        if self.budget_exhausted():
            return self.engines["ollama"]
        
        # 利用可能性チェック（Dockerが動いているか等）
        engine_name = self.AGENT_ROUTING_MAP.get(task_type, "claude_code")
        engine = self.engines[engine_name]
        
        if not await engine.is_available():
            engine = self.fallback_engine(engine_name)
        
        return engine
    
    def classify_task(self, task: Task) -> str:
        """タスク分類ロジック"""
        if task.estimated_hours > 1:
            return "long_running_dev"       # → OpenHands
        if task.context_tokens > 100_000:
            return "long_context"           # → Gemini CLI
        if task.requires_ci_cd:
            return "fast_code_gen"          # → Codex CLI
        if task.budget == 0:
            return "cost_zero"              # → Ollama
        if len(task.pipeline_steps) > 3:
            return "workflow_pipeline"      # → ADK
        return "complex_reasoning"          # → Claude Code (default)


# 全エンジン共通インターフェース
class AgentEngine(Protocol):
    async def is_available(self) -> bool: ...
    async def run(self, task: Task) -> TaskResult: ...
    async def get_cost_estimate(self, task: Task) -> float: ...
    def get_capabilities(self) -> list[str]: ...
```

**Morphic-Agent Agent CLI Orchestration の全体像:**
```
[Morphic-Agentオーケストレーター]
         │
         ├── 長時間開発タスク ──────────→ [OpenHands]
         │   (GitHub issue fix, refactor)    Docker沙箱, 自律実行
         │
         ├── 設計・レビュータスク ─────→ [Claude Code SDK]
         │   (architecture, code review)     headless並列, PTC
         │
         ├── 長文脈分析タスク ─────────→ [Gemini CLI + ADK]
         │   (doc analysis, research)        2M tokens, Grounding
         │
         ├── 高速生成・CI/CDタスク ───→ [Codex CLI]
         │   (bulk codegen, automation)      MCP server, exec
         │
         ├── コスト$0タスク ──────────→ [Ollama]
         │   (drafts, summaries, checks)     ローカル完全無料
         │
         └── [Shared Semantic Memory] ← 全エンジン共通の記憶ハブ
             ・どのエンジンで作業しても同じコンテキスト
             ・会話履歴・決定事項・プロジェクト知識を統一管理
```

---

## 🧠 Semantic Memory & Context Compression — v0.3の記憶革命

> 「全部覚えようとするな、クエリに答えるのに必要な記憶だけを動的に召喚せよ」
> — CPUキャッシュ階層と同じ設計思想

### なぜ単純な要約では駄目か

```
素朴な要約アプローチの失敗:
会話1000回分 → LLMで要約 → 500トークン

問題①: 要約時点では「何が重要か」がわからない
問題②: 要約のたびに情報が劣化（不可逆圧縮）
問題③: 「あの時のニュアンス」が消える
問題④: 要約コスト自体が積み上がる

Hash的アプローチの本質:
情報を「捨てる」のではなく「アクセスを遅延させる」
→ クエリが来た時に必要な記憶だけを動的に召喚
```

### Memory Hierarchy — L1〜L4の階層構造

```
┌────────────────────────────────────────────────────────────────┐
│                    Morphic-Agent Memory Hierarchy                       │
│                                                                  │
│  L1: Active Context (今のトークンウィンドウ)                      │
│  ├── 直近N発言 raw保持                                          │
│  └── ~2,000 tokens                              [最高速・最小]  │
│                                                                  │
│  L2: Semantic Cache (意味的Hash層) ←── 核心                     │
│  ├── 発言をEmbeddingでベクトル化                                 │
│  ├── LSH (Locality Sensitive Hashing) でバケット化              │
│  ├── 類似発言はclusteringして代表ベクトルに圧縮                  │
│  └── 「何を言ったか」→「どの意味空間にいるか」に変換             │
│                                                                  │
│  L3: Structured Facts (知識グラフ層)                             │
│  ├── エンティティ・関係の抽出・正規化                            │
│  └── "Shimizu, project, deadline=3月" のようなトリプル          │
│                                                                  │
│  L4: Cold Storage (完全ログ)                                     │
│  └── 生テキスト全保存、L1-3でmissしたときのみ召喚               │
│                                                 [最低速・最大]  │
└────────────────────────────────────────────────────────────────┘
各層: 上ほど高速・小さい・不完全 / 下ほど低速・大きい・完全
```

### Semantic Fingerprint — LSHによる意味的Hash

```python
import numpy as np
from sentence_transformers import SentenceTransformer

class SemanticMemory:
    """
    通常のHash: 異なる入力 → 異なるHash
    LSH (Locality Sensitive Hashing): 意味が近い入力 → 同じHash
    
    → 「清水建設の話」は何百回しても同じclusterにまとめられ圧縮
    → クエリ時にO(1)に近い速度で関連記憶を取得
    """
    
    def __init__(self):
        self.model = SentenceTransformer("text-embedding-3-small")
        self.store: dict[str, dict] = {}       # hash → {text, embedding, metadata}
        self.cluster_map: dict[str, list] = {} # cluster_id → [hash list]
    
    def add(self, text: str) -> str:
        embedding = self.model.encode(text)   # 1536次元ベクトル
        semantic_hash = self._lsh(embedding)
        
        # 92%以上類似 → 既存エントリを強化（新規保存しない）
        existing = self._find_similar(embedding, threshold=0.92)
        if existing:
            self._reinforce(existing["hash"], text)
            return existing["hash"]
        
        # 新規概念として保存
        self.store[semantic_hash] = {
            "text": text,
            "embedding": embedding,
            "access_count": 1,
            "compressed_summary": None,  # 後で生成
            "created_at": datetime.now(),
            "last_accessed": datetime.now(),
        }
        return semantic_hash
    
    def _lsh(self, embedding: np.ndarray, n_planes: int = 32) -> str:
        """
        LSH: ランダム超平面でバイナリコードに変換
        意味が近い = バイナリコードが似る = 同じHash bucketに入る
        """
        random_planes = np.random.randn(n_planes, len(embedding))
        binary_code = (embedding @ random_planes.T > 0).astype(int)
        return format(int("".join(map(str, binary_code)), 2), "08x")
    
    def retrieve(self, query: str, top_k: int = 5) -> list:
        """クエリに意味的に近い記憶をO(1)に近い速度で取得"""
        query_emb = self.model.encode(query)
        query_hash = self._lsh(query_emb)
        
        # まずHashが同じものを即座に取得（O(1)）
        same_bucket = self.cluster_map.get(query_hash, [])
        
        # 足りなければ近傍bucketをスキャン（O(N), Nは小さい）
        return self._rank_by_similarity(query_emb, same_bucket)[:top_k]
```

### 圧縮の3戦略

**戦略①: Hierarchical Summarization（木構造圧縮）**
```python
"""
Level 0 (葉): "QuickSuiteのUser per Authorライセンスは月$18/user"
Level 1:      "QuickSuiteライセンス構造の詳細"
Level 2:      "清水建設向けコスト試算の前提条件"
Level 3 (根): "清水建設QuickSuiteプロジェクトの概要"

→ 概要質問 → Level3のみ参照 (~10tokens)
→ 詳細質問 → Level0まで掘り下げ (~500tokens)
クエリの性質に応じて「どの深さまで読むか」を動的に決定
"""

class HierarchicalMemory:
    def retrieve_at_depth(self, query: str, max_tokens: int) -> str:
        # トークン予算に応じて木の深さを動的に決定
        depth = self.estimate_required_depth(query, max_tokens)
        return self.tree.traverse_to_depth(query, depth)
```

**戦略②: Forgetting Curve（エビングハウス忘却曲線）**
```python
import math

class ForgettingMemory:
    def retention_score(self, memory: dict) -> float:
        """
        R = e^(-t/S)
        t = 経過時間, S = 記憶の安定性（アクセス頻度・重要度で強化）
        """
        hours_elapsed = (datetime.now() - memory["last_accessed"]).seconds / 3600
        stability = (1.0
                    + memory["access_count"] * 0.5
                    + memory["importance_score"] * 2.0)  # LLMが0-1で評価
        return math.exp(-hours_elapsed / (stability * 24))
    
    def compress_expired(self):
        """保持スコア < 0.3 の記憶を要約してL3（Facts）に昇格後、削除"""
        for hash_id, memory in list(self.store.items()):
            if self.retention_score(memory) < 0.3:
                self._promote_to_facts(memory)  # 要約をL3に保存
                del self.store[hash_id]         # L2から削除
```

**戦略③: Delta Encoding（Git方式差分保存）**
```python
"""
Gitのコミット履歴と同じ発想

Base State: "清水建設プロジェクト = {ライセンス: 未決, 予算: 未定}"
Delta 1:    "+ライセンス決定: User per Author, 50人"
Delta 2:    "+予算承認: $54,000/年"
Delta 3:    "+懸念事項: Lake FormationとのIAM権限"

Current State = Base + Delta1 + Delta2 + Delta3

→ 「現在の状態」だけなら Base + 最新Deltaのみ参照で済む
→ 「経緯が知りたい」ときのみ全Deltaを展開
"""

class DeltaEncoder:
    def record(self, message: str, state_changes: dict) -> Delta:
        return Delta(
            timestamp=datetime.now(),
            message=message,
            changes=state_changes,
            hash=self._hash_state(state_changes)
        )
    
    def reconstruct(self, target_time: datetime = None) -> dict:
        """指定時点の状態を再構築（デフォルト: 最新）"""
        state = self.base_state.copy()
        deltas = self.deltas_until(target_time)
        for delta in deltas:
            state.update(delta.changes)
        return state
```

### ContextZipper — クエリ適応型圧縮

```python
class ContextZipper:
    """
    AIに渡すコンテキストをリアルタイム圧縮するミドルウェア
    目標: 10,000トークンの会話履歴 → 500トークンに圧縮しつつ情報保持
    
    重要: 同じ会話履歴でも、クエリによって異なる最適コンテキストが生成される
    """
    
    def __init__(self, target_tokens: int = 500):
        self.semantic_memory = SemanticMemory()    # L2
        self.fact_store = KnowledgeGraph()         # L3: エンティティ・関係DB
        self.delta_log = DeltaEncoder()            # Delta
        self.target_tokens = target_tokens
    
    def compress(self, conversation_history: list, current_query: str) -> str:
        """クエリに最適化した圧縮コンテキストを動的生成"""
        
        # Step1: クエリに関連する記憶をセマンティック検索
        relevant_memories = self.semantic_memory.retrieve(
            query=current_query, top_k=10
        )
        
        # Step2: 構造化Factsから関連エンティティを取得
        entities = self.extract_entities(current_query)
        relevant_facts = self.fact_store.query(entities)
        
        # Step3: トークン予算内に収まるよう優先度でトリム
        budget = self.target_tokens
        compressed = [f"[Facts] {relevant_facts}"]  # 常に構造化Facts優先
        budget -= self.count_tokens(str(relevant_facts))
        
        for memory in relevant_memories:
            if budget <= 0:
                break
            tokens = self.count_tokens(memory["text"])
            if tokens <= budget:
                compressed.append(memory["text"])
                budget -= tokens
            else:
                # トークン超過 → 要約バージョン使用
                compressed.append(memory["compressed_summary"] or "")
                budget -= 30
        
        return "\n---\n".join(compressed)
    
    def ingest(self, message: str, role: str = "user"):
        """新しい発言を各層に非同期で振り分け"""
        self.semantic_memory.add(message)           # L2
        self.fact_store.update_from_text(message)   # L3
        self.delta_log.record(message, {})          # Delta


# 使用例: マルチAI環境でのコンテキスト共有
zipper = ContextZipper(target_tokens=800)

def ask_any_ai(ai: str, question: str, user_id: str = "ryo"):
    """どのAIに聞いても同じ文脈を持つ"""
    
    # 関連記憶を圧縮して取得
    context = zipper.compress([], question)
    
    system = f"""あなたはユーザーのAIアシスタントです。
以下の記憶・文脈を持っています:
{context}"""
    
    # 各AIに同じ文脈を注入して呼び出す
    if ai == "claude":
        response = anthropic_client.messages.create(...)
    elif ai == "gpt":
        response = openai_client.chat.completions.create(...)
    elif ai == "gemini":
        response = genai_model.generate_content(...)
    
    # 新しい情報をメモリに追加
    zipper.ingest(f"Q: {question}\nA: {answer}")
    return answer

# 使い方: コンテキストが自動的に引き継がれる
ask_any_ai("claude", "Shimizuプロジェクトの現状は？")
ask_any_ai("gpt",    "↑の内容でメール文面を作って")   # ← 文脈引き継ぎ
ask_any_ai("gemini", "コスト試算も加えてレポートにして")# ← さらに引き継ぎ
```

### 最先端研究との接続

| 研究 | 内容 | Morphic-Agentへの応用 |
|---|---|---|
| **MemGPT / Letta** | OSのページング思想をLLMに適用。L1/L2/L3階層を先行実装 | `pip install letta` で即使用可能 |
| **Mamba / SSM** | 無限の文脈を固定サイズの「状態ベクトル」に圧縮し続ける | Semantic Hashの理論的根拠 |
| **Titans (Google, 2024)** | "驚き度(surprise)が高い情報だけをメモリに書き込む" 選択的記憶 | ForgettingCurveのimportance_scoreに応用 |
| **mem0** | LLMで会話から自動抽出・ベクトルDB保存 | L2の実装として即使用可能 |

**推奨スタート構成:**
```python
# Phase 1: mem0だけで8割の問題を解決
from mem0 import Memory
memory = Memory()  # 全AI共通の記憶

# Phase 2: pgvector + ContextZipperで精度向上
# Phase 3: Knowledge Graph + Delta Encodingで完全実装
```

---

## 🔧 Core Components

### 1. Task Graph Engine

```python
from langgraph.graph import StateGraph, END

class TaskGraphEngine:
    """添付画像のGPS成功/失敗分岐を汎化したDAG実装"""
    def build_graph(self, goal: str) -> StateGraph:
        graph = StateGraph(AgentState)
        graph.add_conditional_edges(
            "execution",
            self.route_after_execution,
            {
                "success":    "observation",
                "failure":    "fallback_selection",
                "need_tool":  "tool_acquisition",
                "need_human": "human_checkpoint",
            }
        )
        return graph

# 組み込みツール（vibe-local インスパイア + LAEE v0.4）
BUILT_IN_TOOLS = [
    # ── 基本ツール ──
    "bash", "bash_background",        # シェル実行（同期・非同期）
    "file_read", "file_write", "file_edit",  # ファイル操作
    "glob", "grep",                   # 検索
    "web_fetch", "web_search",        # Web
    "notebook_edit",                  # Jupyter
    "sub_agent", "parallel_agents",   # エージェント生成・並列実行
    "task_create", "task_list", "task_get", "task_update",  # タスク管理
    "ask_user_question",              # 明示的ユーザー確認
    # ── LAEE ローカル自律実行ツール (v0.4) ──
    "shell_exec", "shell_background", "shell_stream", "shell_pipe",  # シェル拡張
    "fs_read", "fs_write", "fs_edit", "fs_delete", "fs_move",       # FS拡張
    "fs_glob", "fs_watch", "fs_tree",                                # FS検索・監視
    "browser_navigate", "browser_click", "browser_type",              # ブラウザ自動化
    "browser_screenshot", "browser_extract", "browser_pdf",           # ブラウザ取得
    "system_process_list", "system_process_kill",                     # プロセス管理
    "system_resource_info", "system_clipboard_get",                   # システム情報
    "system_clipboard_set", "system_notify", "system_screenshot",     # システム操作
    "dev_git", "dev_docker", "dev_pkg_install", "dev_env_setup",      # 開発ツール
    "gui_applescript", "gui_open_app", "gui_screenshot_ocr",          # GUI自動化
    "cron_schedule", "cron_once", "cron_list", "cron_cancel",         # スケジュール
]
```

---

### 2. Parallel Execution Engine

**Cursor の鉄則: "DEFAULT TO PARALLEL"**
> 並列ツール実行は3-5倍高速。順次はAの出力がBに必要な場合のみ許可。

```python
class ParallelExecutionEngine:
    async def execute_task_group(self, tasks: list[Task]) -> list[Result]:
        dep_graph = self.build_dependency_graph(tasks)
        # 独立タスクは一斉並列実行
        results = await asyncio.gather(
            *[self.execute_single(t) for t in dep_graph.get_independent_tasks()],
            return_exceptions=True
        )
        return results
```

---

### 3. Interactive Planning System

**Devin 2.0 + Windsurf Cascade から学ぶ**

```python
class InteractivePlanner:
    async def plan_and_confirm(self, goal: str) -> ExecutionPlan:
        recon = await self.reconnaissance(goal)
        plan  = await self.generate_plan(goal, recon)
        
        # コスト見積もり付きで人間確認
        summary = f"""
## 実行計画: {goal}
{self._format_steps(plan.steps)}

### コスト見積もり
- 推定コスト: ${plan.estimated_cost:.4f}
- 使用モデル: {plan.model_allocation}
- リスク: {self._format_risks(plan.risks)}

承認しますか? [Y/n/edit]
"""
        return await self.ask_user_confirmation(summary, plan)

    async def background_planner(self, state: AgentState) -> None:
        """Windsurf式: バックグラウンドで長期計画を継続改善"""
        while state.is_running:
            state.update_plan(await self.refine_long_term_plan(state))
            await asyncio.sleep(5)
```

---

### 4. Multi-LLM Router with Local Support (Ollama優先)

**vibe-local から学ぶ: ローカルLLMでAPIコスト$0**

```python
from litellm import completion

class MultiLLMRouter:
    """LiteLLM統一API。Ollamaを最優先にすることでコスト最小化。"""
    
    MODEL_TIERS = {
        "free": [
            "ollama/qwen3:8b",          # 16GBマシン向け (vibe-local推奨)
            "ollama/qwen3-coder:30b",   # 32GB / コーディング特化
            "ollama/deepseek-r1:8b",    # 推論特化
            "ollama/llama3.2:3b",       # 超軽量・高速
            "ollama/phi4:14b",          # MS高性能ローカル
        ],
        "low": [
            "claude-haiku-4-5-20251001",   # $0.25/1M
            "gemini/gemini-2.0-flash",
        ],
        "medium": [
            "claude-sonnet-4-6",           # $3/1M (キャッシュ$0.30)
            "gpt-4o-mini",
            "gemini/gemini-2.5-pro",
        ],
        "high": [
            "claude-opus-4-6",
            "gpt-4o",
        ],
    }
    
    TASK_MODEL_MAP = {
        "simple_qa":       ("free", "low"),
        "code_generation": ("free", "medium"),   # qwen3-coder優先
        "complex_reasoning":("medium", "high"),
        "file_operation":  ("free", "low"),
        "long_context":    ("medium",),           # Gemini Pro推奨
        "multimodal":      ("medium", "high"),
    }
    
    async def route(self, task: Task, budget: float) -> str:
        task_type = self.classify_task(task)
        for tier in self.TASK_MODEL_MAP.get(task_type, ("free", "medium")):
            for model in self.MODEL_TIERS[tier]:
                if self.is_available(model) and self.fits_budget(model, budget):
                    return model
        return "ollama/qwen3:8b"  # 常に無料でフォールバック
    
    def is_ollama_running(self) -> bool:
        try:
            return requests.get("http://127.0.0.1:11434/api/tags", timeout=1).ok
        except:
            return False
    
    async def call(self, model: str, messages: list, **kwargs) -> str:
        if model.startswith("ollama/"):
            kwargs["api_base"] = "http://127.0.0.1:11434"
        response = await completion(model=model, messages=messages,
                                    cache={"type": "disk"}, **kwargs)
        return response.choices[0].message.content
```

**Ollamaモデル推奨 (vibe-local 調査結果):**

| マシンスペック | 推奨モデル | 特徴 |
|---|---|---|
| 8GB RAM | `qwen3:8b` | 軽量・高性能・日本語対応 |
| 16GB RAM | `qwen3:8b` + `deepseek-r1:8b` | コーディング+推論 |
| 32GB RAM | `qwen3-coder:30b` | プロフェッショナルコーディング |
| GPU 8GB+ | `llama3.3:70b` | 最高品質ローカル |

```bash
# セットアップ
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull qwen3:8b           # 16GBマシン向け
ollama pull qwen3-coder:30b   # コーディング特化
ollama pull deepseek-r1:8b    # 推論特化
```

---

### 5. Cost Control System

```yaml
# morphic_agent_cost_config.yaml
global:
  monthly_budget_usd: 50
  circuit_breaker_pct: 95     # これを超えたら全API停止
  alert_threshold_pct: 80

model_preference:
  default_cascade:
    - ollama/qwen3:8b          # 1st: ローカル（無料）
    - claude-haiku-4-5         # 2nd: 格安API
    - claude-sonnet-4-6        # 3rd: 複雑タスク
    - claude-opus-4-6          # Last: 最終手段のみ

local_first: true              # Ollama利用可能なら必ず最優先
auto_downgrade: true           # 予算80%超えで自動ダウングレード
cache_breakpoints: true        # KVキャッシュ最適化有効
```

**コスト可視化指標:**
```python
CostMetrics = {
    "total_spent_today":   float,
    "budget_remaining":    float,
    "local_usage_rate":    float,  # ローカル使用率（高いほど良い）
    "cache_hit_rate":      float,  # KVキャッシュヒット率
    "savings_from_local":  float,  # ローカルLLMによる節約額
    "savings_from_cache":  float,  # キャッシュによる節約額
    "cost_per_task_avg":   float,
}
```

---

### 6. Skill / Tool Marketplace

```python
class ToolMarketplace:
    async def auto_discover_tools(self, failed_task: Task) -> list[Tool]:
        """タスク失敗時に必要なツールを自律的に探索・取得"""
        needed = await self.analyze_failure(failed_task)
        
        # 複数ソースを並列検索
        candidates = await asyncio.gather(
            self.search_mcp_registry(needed),
            self.search_pypi(needed),
            self.search_npm(needed),
            self.search_github_actions(needed),
        )
        
        ranked = self.rank_candidates(candidates)
        
        # 設定により自動/手動承認
        approved = ranked[:3] if self.config.auto_install else \
                   await self.ask_user_approval(ranked[:5])
        
        installed = []
        for spec in approved:
            tool = await self.install_tool(spec)
            self.registry.register(tool)
            await self.publish_to_marketplace(tool)  # 他エージェントも使える
            installed.append(tool)
        return installed

# ツールソース優先順位
TOOL_SOURCES = [
    "MCP Registry (1000+ prebuilt servers)",    # 最優先
    "vibe-local compatible Python stdlib tools", # 依存ゼロ
    "PyPI / npm packages",                       # 必要時
    "Custom OpenAPI definitions",                # ユーザー定義
]
```

---

### 7. Cross-Platform Context Bridge

**問題:** Claude.ai / ChatGPT / Cursor / Geminiのコンテキストが断絶。毎回コピペ記憶が必要。
**解決:** Morphic-Agentをすべてのコンテキストのハブとして、MCPサーバー経由で全プラットフォームから接続。

```python
class ContextBridge:
    async def export_to_platform(self, platform: str) -> str:
        ctx = self.get_current_context()
        formatters = {
            "claude_code": self.format_as_claude_md,
            "chatgpt":     self.format_for_chatgpt,
            "cursor":      self.format_for_cursor,
            "gemini":      self.format_for_gemini,
        }
        return formatters[platform](ctx)
    
    def format_as_claude_md(self, ctx) -> str:
        """CLAUDE.md形式でコンテキストをエクスポート（Claude Code向け）"""
        return f"# Morphic-Agent Context\n## Goal: {ctx.goal}\n## State: ...\n"

class ClipboardContextInjector:
    """コピペ操作を検知してMorphic-Agentコンテキストを自動付与（Chrome Extension）"""
    def on_paste(self, target_app: str, content: str) -> str:
        summary = self.morphic-agent.get_relevant_context(content)
        return f"{summary}\n\n{content}"
```

---

### 8. Self-Evolution Engine

```python
class SelfEvolutionEngine:
    """
    Level 1 Tactical:  タスク内リアルタイム適応（即時エラーリカバリー）
    Level 2 Strategic: セッション間学習（プロンプト・モデル選択改善）
    Level 3 Systemic:  システム全体の能力拡張（ツール自律取得）
    """
    
    async def tactical_recovery(self, failed: Action) -> Action:
        """Devin式Self-Healing: エラーを読んで即座に代替手段"""
        analysis    = await self.analyze_error(failed.error)
        alternatives = self.strategy_db.get_alternatives(failed.tool, analysis)
        return alternatives[0] if alternatives else self.ask_user(failed)
    
    async def update_strategy(self, session: Session) -> None:
        """セッション後: 失敗パターン分析 → プロンプト改善 → モデル選択更新"""
        failures = self.analyze_failures(session.trace)
        await self.evolve_prompt_templates(failures)
        await self.update_model_preferences(session)
    
    async def systemic_evolution(self, sessions: list[Session]) -> Report:
        """長期: ツールギャップを検知して自律取得"""
        tool_gaps = self.identify_tool_gaps(sessions)
        for gap in tool_gaps:
            if new_tool := await self.marketplace.auto_discover_tools(gap):
                await self.register_and_test(new_tool)
        return self.generate_evolution_report(sessions)
```

**学習データ:**
```json
{
  "task_id": "nav_2026_001",
  "model_used": "ollama/qwen3:8b",
  "cost_usd": 0.00,
  "cache_hit_rate": 0.87,
  "user_rating": 4.5,
  "evolution_insights": {
    "should_add_tool": "real_time_traffic_api",
    "prompt_improvement": "Add 'check real-time data' to route planning template",
    "model_recommendation": "ollama/qwen3:8b is sufficient for this task type"
  }
}
```

---

### 9. A2A (Agent-to-Agent) Communication

```python
# Google A2A Protocol 準拠
AGENT_ROLES = {
    "orchestrator": "タスク分解・割り当て・統合",
    "research":     "情報収集・ウェブ検索・文書分析",
    "code":         "コード生成・デバッグ・テスト",
    "qa":           "品質検証・セキュリティレビュー",
    "report":       "成果物生成・要約",
    "planner":      "バックグラウンド計画改善（Windsurf式）",
}
```

---

### 10. Local Autonomous Execution Engine (LAEE) — v0.4 NEW

> **OpenClaw的発想**: エージェントがユーザーのローカルPCを「手足」として直接操作する。
> Docker沙箱ではなく、**ユーザーの実マシン上でリアルタイムにタスクを実行**する。
> 安全性はユーザーの自己責任。3段階の承認モードで制御。

```
なぜ必要か:
- OpenHands はDocker沙箱 → 安全だがユーザーのローカル環境を触れない
- 実際のユースケースの80%は「自分のPCで何かしてほしい」
  - "brew で〇〇をインストールして環境構築して"
  - "このフォルダの画像を全部リサイズして"
  - "Chromeで〇〇を検索してスプレッドシートにまとめて"
  - "毎朝9時にSlackの未読をサマリーして"
- ユーザーが「自己責任でOK」と言えば、full-autoで全自動化可能
```

#### 承認モード (Approval Mode)

```python
from enum import Enum

class ApprovalMode(Enum):
    FULL_AUTO = "full-auto"                  # ユーザーが全リスクを受容。確認なし
    CONFIRM_DESTRUCTIVE = "confirm-destructive"  # 破壊的操作のみ確認
    CONFIRM_ALL = "confirm-all"              # 全操作を確認

class RiskLevel(Enum):
    SAFE = 0        # 読み取り専用・完全可逆（ls, cat, grep, screenshot）
    LOW = 1         # ファイル作成・プロセス起動（mkdir, touch, open）
    MEDIUM = 2      # ファイル変更・パッケージインストール（edit, brew install）
    HIGH = 3        # ファイル削除・プロセス強制終了（rm, kill -9, config変更）
    CRITICAL = 4    # 再帰削除・システム設定・認証情報アクセス（rm -rf, sudo）

class ApprovalEngine:
    """承認モードとリスクレベルの組み合わせで実行可否を判定"""

    APPROVAL_MATRIX = {
        # ApprovalMode →  SAFE  LOW  MED  HIGH  CRIT
        "full-auto":          [True, True, True, True, True],
        "confirm-destructive": [True, True, True, False, False],
        "confirm-all":        [True, False, False, False, False],
    }

    async def check(self, action: Action, mode: ApprovalMode) -> bool:
        needs_approval = not self.APPROVAL_MATRIX[mode.value][action.risk.value]
        if needs_approval:
            return await self.ask_user(
                action=action.description,
                risk=action.risk.name,
                reversible=action.undo_hint or "N/A",
            )
        return True
```

#### ツールカテゴリ

```python
# ローカル実行ツール定義 — エージェントの「手足」
LOCAL_TOOLS = {
    # ── シェル実行 ──
    "shell_exec":        {"risk": "MEDIUM", "desc": "コマンド同期実行"},
    "shell_background":  {"risk": "LOW",    "desc": "バックグラウンドジョブ起動"},
    "shell_stream":      {"risk": "MEDIUM", "desc": "stdout/stderrをリアルタイムストリーム"},
    "shell_pipe":        {"risk": "MEDIUM", "desc": "パイプライン構築・実行"},

    # ── ファイルシステム ──
    "fs_read":           {"risk": "SAFE",   "desc": "ファイル読み取り"},
    "fs_write":          {"risk": "MEDIUM", "desc": "ファイル書き込み"},
    "fs_edit":           {"risk": "MEDIUM", "desc": "部分編集（sed的）"},
    "fs_delete":         {"risk": "HIGH",   "desc": "ファイル/ディレクトリ削除"},
    "fs_move":           {"risk": "MEDIUM", "desc": "移動・リネーム"},
    "fs_glob":           {"risk": "SAFE",   "desc": "パターン検索"},
    "fs_watch":          {"risk": "LOW",    "desc": "ファイル変更監視（watchdog）"},
    "fs_tree":           {"risk": "SAFE",   "desc": "ディレクトリ構造表示"},

    # ── ブラウザ自動化（Playwright） ──
    "browser_navigate":  {"risk": "LOW",    "desc": "URLへ移動"},
    "browser_click":     {"risk": "MEDIUM", "desc": "要素クリック"},
    "browser_type":      {"risk": "MEDIUM", "desc": "テキスト入力"},
    "browser_screenshot":{"risk": "SAFE",   "desc": "スクリーンショット取得"},
    "browser_extract":   {"risk": "SAFE",   "desc": "ページデータ抽出"},
    "browser_pdf":       {"risk": "LOW",    "desc": "ページをPDF保存"},

    # ── システム制御 ──
    "system_process_list":  {"risk": "SAFE",   "desc": "プロセス一覧"},
    "system_process_kill":  {"risk": "HIGH",   "desc": "プロセス終了"},
    "system_service_status":{"risk": "SAFE",   "desc": "サービス状態確認"},
    "system_resource_info": {"risk": "SAFE",   "desc": "CPU/メモリ/ディスク情報"},
    "system_clipboard_get": {"risk": "SAFE",   "desc": "クリップボード読み取り"},
    "system_clipboard_set": {"risk": "LOW",    "desc": "クリップボード書き込み"},
    "system_notify":        {"risk": "LOW",    "desc": "デスクトップ通知"},
    "system_screenshot":    {"risk": "SAFE",   "desc": "画面全体スクリーンショット"},

    # ── 開発ツール ──
    "dev_git":           {"risk": "MEDIUM", "desc": "Git操作（add/commit/push等）"},
    "dev_docker":        {"risk": "MEDIUM", "desc": "Docker操作"},
    "dev_pkg_install":   {"risk": "MEDIUM", "desc": "パッケージインストール（brew/pip/npm）"},
    "dev_pkg_search":    {"risk": "SAFE",   "desc": "パッケージ検索"},
    "dev_env_setup":     {"risk": "MEDIUM", "desc": "開発環境セットアップ"},

    # ── GUI自動化（macOS） ──
    "gui_applescript":   {"risk": "MEDIUM", "desc": "AppleScript実行"},
    "gui_open_app":      {"risk": "LOW",    "desc": "アプリケーション起動"},
    "gui_screenshot_ocr":{"risk": "SAFE",   "desc": "画面キャプチャ+OCR"},
    "gui_accessibility": {"risk": "MEDIUM", "desc": "Accessibility APIで要素操作"},

    # ── スケジュール ──
    "cron_schedule":     {"risk": "MEDIUM", "desc": "定期タスク登録"},
    "cron_once":         {"risk": "LOW",    "desc": "ワンショットタイマー"},
    "cron_list":         {"risk": "SAFE",   "desc": "登録済みジョブ一覧"},
    "cron_cancel":       {"risk": "LOW",    "desc": "ジョブキャンセル"},
}
```

#### 実行フロー

```python
class LocalExecutor:
    """
    LAEEの中核。LLMが生成したアクション計画をローカルマシンで実行する。
    全アクションはAuditLogに記録。リスク評価→承認→実行→観察の4ステップ。
    """

    def __init__(self, approval_mode: ApprovalMode = ApprovalMode.CONFIRM_DESTRUCTIVE):
        self.approval = ApprovalEngine()
        self.mode = approval_mode
        self.audit = AuditLog()          # 全操作ログ
        self.undo_stack: list[UndoAction] = []  # 可逆操作のundo情報

    async def execute(self, action: Action) -> Observation:
        # 1. リスク評価
        risk = self.assess_risk(action)

        # 2. 承認チェック（モードに応じて自動 or ユーザー確認）
        approved = await self.approval.check(action, self.mode)
        if not approved:
            return Observation(status="denied", result="User denied this action")

        # 3. 実行前スナップショット（undo用）
        if action.reversible:
            self.undo_stack.append(action.create_undo())

        # 4. 実行
        try:
            result = await self.run_tool(action.tool, action.args)
            self.audit.log(action, result, risk)
            return Observation(status="success", result=result)
        except Exception as e:
            self.audit.log(action, str(e), risk, success=False)
            return Observation(status="error", result=str(e))

    async def undo_last(self) -> Observation:
        """直前の操作を取り消す（可逆操作のみ）"""
        if not self.undo_stack:
            return Observation(status="error", result="Nothing to undo")
        undo = self.undo_stack.pop()
        return await self.run_tool(undo.tool, undo.args)


class AuditLog:
    """全アクションの不変ログ。セキュリティ・デバッグ・進化学習に使用"""
    LOG_PATH = ".morphic/audit_log.jsonl"

    def log(self, action: Action, result: str, risk: RiskLevel, success: bool = True):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "tool": action.tool,
            "args": action.args,
            "risk": risk.name,
            "success": success,
            "result_summary": result[:500],  # 長すぎる結果は切り詰め
            "approval_mode": self.current_mode.value,
        }
        # append-only JSONL (Manus原則3: ファイルを無限コンテキストとして使う)
        with open(self.LOG_PATH, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

#### ユースケース例

```
# ユーザー: "開発環境をセットアップして"
# LAEE実行フロー（full-autoモード）:

1. shell_exec: brew install python@3.12 node docker
2. dev_pkg_install: pip install uv && uv sync
3. shell_exec: docker compose up -d
4. dev_git: git clone ... && git checkout -b feature/xxx
5. shell_exec: uv run pytest  # 動作確認
6. system_notify: "開発環境セットアップ完了 ✓"

# ユーザー: "毎朝9時にSlackの未読をサマリーして"
# LAEE実行フロー:

1. browser_navigate: slack.com/api/conversations.history
2. browser_extract: 未読メッセージ取得
3. LLM: サマリー生成
4. system_clipboard_set: サマリーをクリップボードに
5. system_notify: "Slackサマリー準備完了"
6. cron_schedule: 上記を毎朝9:00に繰り返し

# ユーザー: "このフォルダの画像を全部リサイズして"
# LAEE実行フロー:

1. fs_glob: ./images/**/*.{png,jpg,jpeg}
2. shell_exec: magick mogrify -resize 800x600 (並列)
3. fs_tree: 処理結果確認
4. system_notify: "42枚の画像をリサイズ完了"
```

---

## 🧩 Prompt Engineering — 業界ベストプラクティス集

> `x1xhlol/system-prompts-and-models-of-ai-tools` (116k⭐) の分析から抽出

### Cursor (Agent Prompt 2025-09-03)
```
1. "Keep going until query is COMPLETELY resolved"
   → 解決するまで止まらない

2. "DEFAULT TO PARALLEL: always parallel unless output of A required for B"
   → 並列がデフォルト、順次には理由が必要

3. "If you say you're about to do something, do it in the same turn"
   → 宣言したら即実行。宣言だけしない

4. "Check off TODOs before reporting progress"
   → 進捗報告前にtodo.mdを更新

5. "NEVER refer to tool names when speaking to USER"
   → ユーザーにはツール名でなく自然言語で説明
```

### Windsurf Cascade
```
1. Code/Chatの2モードで「変更あり/なし」を明確に分離
2. バックグラウンド計画エージェントで全体最適を維持
3. .windsurfrules的なルールファイルでプロジェクト固有制約を管理
4. 自動生成Memoriesでコーディングスタイル・APIを永続学習
5. "Before changes, present plan and ask for confirmation"
```

### Devin 2.0
```
1. Interactive Planning: 実行前に計画+コード引用で提示
2. Self-assessed confidence: タスク後に自己評価スコアを報告
3. Planning Checkpoint: 高リスク変更前は人間確認必須
4. 各タスクを独立VMで実行（隔離・並列）
5. Wiki/Search: コードベース構造を自動学習
```

### Manus Context Engineering Blog
```
1. KV-cacheヒット率が最重要メトリクス（10倍コスト差）
2. ツールは削除せずマスクで制御
3. ファイルシステムを無限の外部メモリとして使う
4. todo.mdでアテンションを意図的に操作
5. 観察に多様性を入れてドリフトを防ぐ
6. "Stochastic Graduate Descent": 完璧より動作、学習しながら改善
```

---

## 📁 Project Structure — Clean Architecture (v0.4)

> **4層分離 + TDD**: 依存は常に内側へ。domain層はフレームワーク依存ゼロ。

```
morphic-agent/
├── CLAUDE.md                          # プロジェクトの"憲法"
├── pyproject.toml                     # uv プロジェクト定義
├── docker-compose.yml                 # PostgreSQL+pgvector, Redis, Neo4j
├── .env.example
│
├── domain/                            # Layer 1: 純粋ビジネスロジック（依存ゼロ）
│   ├── entities/
│   │   ├── task.py                    # TaskEntity, SubTask (純粋Pydantic)
│   │   ├── execution.py              # Action, Observation, UndoAction
│   │   ├── memory.py                 # MemoryEntry
│   │   └── cost.py                   # CostRecord
│   ├── value_objects/
│   │   ├── risk_level.py             # RiskLevel (5段階)
│   │   ├── approval_mode.py          # ApprovalMode (3段階)
│   │   └── model_tier.py             # ModelTier, TaskType
│   ├── ports/                         # ABC — 依存性逆転インターフェース
│   │   ├── task_repository.py
│   │   ├── llm_gateway.py
│   │   ├── local_executor.py
│   │   ├── audit_logger.py
│   │   ├── memory_repository.py
│   │   └── cost_repository.py
│   └── services/                      # ドメインサービス（純粋関数）
│       ├── risk_assessor.py           # LAEE リスク評価
│       └── approval_engine.py         # LAEE 承認判定
│
├── application/                       # Layer 2: ユースケース
│   ├── use_cases/
│   │   ├── execute_task.py            # タスク実行フロー
│   │   ├── run_local_action.py        # LAEE ローカル実行
│   │   ├── route_to_model.py          # LLMルーティング
│   │   └── search_memory.py           # セマンティック検索
│   └── dto/                           # レイヤー間データ転送
│
├── infrastructure/                    # Layer 3: ポートの実装
│   ├── persistence/
│   │   ├── database.py                # SQLAlchemy async engine
│   │   ├── models.py                  # ORM models (≠ domain entities)
│   │   ├── task_repo.py               # TaskRepository 実装
│   │   ├── cost_repo.py               # CostRepository 実装
│   │   └── memory_repo.py             # MemoryRepository 実装
│   ├── llm/
│   │   ├── litellm_gateway.py         # LLMGateway 実装 (LiteLLM)
│   │   ├── ollama_manager.py          # Ollama ライフサイクル管理
│   │   └── cost_tracker.py            # LiteLLM callback コスト追跡
│   ├── local_execution/               # LAEE ツール実装 (v0.4)
│   │   ├── executor.py                # LocalExecutorPort 実装
│   │   ├── audit_log.py               # AuditLogger 実装 (JSONL)
│   │   └── tools/
│   │       ├── shell_tools.py         # shell_exec/background/stream/pipe
│   │       ├── fs_tools.py            # fs_read/write/edit/delete
│   │       ├── browser_tools.py       # Playwright 自動化
│   │       ├── system_tools.py        # process/resource/clipboard
│   │       ├── dev_tools.py           # git/docker/pkg管理
│   │       ├── gui_tools.py           # macOS AppleScript
│   │       └── cron_tools.py          # APScheduler 定期実行
│   ├── memory/
│   │   ├── mem0_adapter.py            # mem0 → MemoryRepository
│   │   ├── neo4j_adapter.py           # Neo4j → KnowledgeGraph
│   │   └── context_bridge.py          # クロスプラットフォーム
│   └── agent_cli/                     # Agent CLI ドライバー (v0.3)
│       ├── openhands_driver.py
│       ├── claude_code_driver.py
│       ├── gemini_adk_driver.py
│       └── codex_cli_driver.py
│
├── interface/                         # Layer 4: エントリーポイント
│   ├── api/
│   │   ├── main.py                    # FastAPI app factory
│   │   ├── deps.py                    # DI (ポート→実装の注入)
│   │   ├── routes/
│   │   │   ├── tasks.py
│   │   │   ├── cost.py
│   │   │   └── memory.py
│   │   └── websocket.py
│   └── cli/
│       └── main.py                    # CLI エントリーポイント
│
├── shared/                            # 横断的関心事
│   └── config.py                      # pydantic-settings 設定
│
├── tests/                             # TDD テストスイート
│   ├── unit/domain/                   # DB不要・高速 (45テスト, 0.06秒)
│   │   ├── test_entities.py
│   │   ├── test_risk_assessor.py
│   │   └── test_approval_engine.py
│   ├── unit/application/              # ポートをモック
│   ├── integration/                   # Docker Compose必要
│   └── e2e/                           # 全層統合テスト
│
├── migrations/                        # Alembic (async)
│
└── ui/                                # Next.js 15 ダーク・シックUI
    ├── app/
    │   ├── dashboard/
    │   ├── task-graph/                # React Flowビジュアライザー
    │   ├── marketplace/
    │   └── evolution/
    └── components/
```

**依存ルール:**
```
Interface → Application → Domain ← Infrastructure
                                    (依存性逆転)

✅ domain/ はフレームワーク依存ゼロ（SQLAlchemy, FastAPI, LiteLLM を import しない）
✅ infrastructure/ は domain/ports/ の ABC を実装する
✅ application/ は domain/ のエンティティとポートだけ使う
✅ interface/ は application/ のユースケースを呼ぶ（DI でポート→実装を注入）
```

---

## 🚀 Tech Stack

| カテゴリ | 技術 | 選定理由 |
|---|---|---|
| エージェント基盤 | **LangGraph** | DAG・状態管理・並列実行 |
| LLM統合 | **LiteLLM** | Ollama含む100+モデル統一API |
| ローカルLLM | **Ollama** | vibe-local実績、$0運用の鍵 |
| 構造化出力 | **Instructor** | Pydantic型安全 |
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
| ローカル実行 | **LAEE** | シェル・FS・ブラウザ・GUI・cronを統合制御 |
| ブラウザ自動化 | **Playwright** | Chromium/Firefox/WebKit、headless対応 |
| GUI自動化 | **AppleScript / osascript** | macOSネイティブ。Linux: xdotool |
| ファイル監視 | **watchdog** | クロスプラットフォーム inotify/FSEvents |
| スケジューラ | **APScheduler** | cron式定期実行 + ワンショット |

---

## 🎨 UI Design — "Mission Control for Intelligence"

```typescript
export const morphic-agentTheme = {
  colors: {
    background:   '#0A0A0F',  // 深宇宙ブラック
    surface:      '#12121A',  // ダークネイビー
    border:       '#1E1E2E',  // 微細ボーダー
    accent:       '#6366F1',  // インディゴ（主要アクション）
    success:      '#10B981',  // エメラルド（完了）
    warning:      '#F59E0B',  // アンバー（コスト警告）
    danger:       '#EF4444',  // レッド（失敗）
    info:         '#38BDF8',  // スカイブルー（実行中）
    localFree:    '#34D399',  // ブライトグリーン（LOCAL FREE表示）
    text:         '#E2E8F0',
    textMuted:    '#94A3B8',
  },
  fonts: {
    heading: "'Geist', 'Inter', sans-serif",
    mono:    "'JetBrains Mono', 'Fira Code', monospace",
  },
}

// タスクノード視覚状態
const TaskNodeStyles = {
  pending:  { border: '#2D2D42', icon: '⏳' },
  running:  { border: '#38BDF8', icon: '⚡', pulse: true },
  success:  { border: '#10B981', icon: '✓' },
  failed:   { border: '#EF4444', icon: '✗' },
  fallback: { border: '#F59E0B', icon: '↻' },
  // ローカルLLM使用中は「FREE」バッジを表示
  local:    { badge: 'FREE', badgeColor: '#34D399' },
}
```

**画面レイアウト:**
```
┌─────────────────────────────────────────────────────────┐
│ [Morphic-Agent]  [New Task]  [Marketplace]  [Settings]          │ ← ヘッダー
├──────────┬──────────────────────────────┬──────────────┤
│ Tasks    │   TASK GRAPH VISUALIZER      │ Context      │
│ ├ Active │                              │ Bridge       │
│ │ ○ A   │  [Goal]──[A]──[A1]──[✓]    │ ─────────    │
│ │ ─ B   │        └─[B]──[B1]──[↻]   │ Cost: $0.00  │
│ ├History │                              │ LOCAL: 87%   │
│ └ Tools  │  [Execute] [Plan] [Pause]    │ Cache: 92%   │
├──────────┴──────────────────────────────┴──────────────┤
│ ⚡ Running: sub_task_B  |  🔋 qwen3:8b (LOCAL FREE)    │ ← ステータスバー
└─────────────────────────────────────────────────────────┘
```

---

## ⚙️ Environment Variables

```env
# LLM APIs（すべてオプション、Ollamaだけでも動作する）
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GOOGLE_GEMINI_API_KEY=

# ローカルLLM (Ollama)
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_DEFAULT_MODEL=qwen3:8b
OLLAMA_CODING_MODEL=qwen3-coder:30b
LOCAL_FIRST=true              # Ollamaが使えるなら最優先

# Agent CLI Orchestration (v0.3)
OPENHANDS_BASE_URL=http://localhost:3000     # OpenHands local
OPENHANDS_MODEL=claude-sonnet-4-6           # OpenHandsが使うモデル
CLAUDE_CODE_SDK_ENABLED=true                # Claude Code SDK使用
GEMINI_CLI_ENABLED=true                     # Gemini CLI使用
CODEX_CLI_ENABLED=true                      # OpenAI Codex CLI使用
AGENT_DEFAULT_ENGINE=claude_code            # デフォルトエンジン

# Semantic Memory (v0.3)
SEMANTIC_MEMORY_BACKEND=mem0               # mem0 | qdrant | custom
MEM0_API_KEY=                              # mem0 Cloud (オプション)
MEMORY_TARGET_TOKENS=800                   # ContextZipper圧縮目標
MEMORY_RETENTION_THRESHOLD=0.3            # 忘却曲線閾値

# Database
DATABASE_URL=postgresql://morphic-agent:morphic-agent@localhost:5432/morphic-agent
REDIS_URL=redis://localhost:6379
QDRANT_URL=http://localhost:6333

# Cost Control
DEFAULT_MONTHLY_BUDGET_USD=50
DEFAULT_TASK_BUDGET_USD=1.0
AUTO_DOWNGRADE_ON_BUDGET=true
CACHE_BREAKPOINTS_ENABLED=true

# Local Autonomous Execution Engine (LAEE v0.4)
LAEE_ENABLED=true                     # LAEE有効化
LAEE_APPROVAL_MODE=confirm-destructive # full-auto | confirm-destructive | confirm-all
LAEE_AUDIT_LOG_PATH=.morphic/audit_log.jsonl
LAEE_UNDO_ENABLED=true               # 可逆操作のundo機能
LAEE_MAX_CONCURRENT_SHELLS=10        # 同時バックグラウンドジョブ数
LAEE_BROWSER_HEADLESS=true           # Playwright headless mode
LAEE_GUI_ENABLED=true                # GUI自動化（macOS AppleScript）
LAEE_CRON_ENABLED=true               # スケジュール機能

# Morphic-Agent Settings
Morphic-Agent_ENV=development
AUTO_TOOL_INSTALL=false       # true: 自動, false: 承認制
EVOLUTION_ENABLED=true
PLANNING_MODE=interactive     # interactive | auto | disabled
TASK_SANDBOX=docker
```

---

## 🚀 Development Phases (v0.3更新版)

### Phase 1: Foundation (Week 1-2) — まず動かす
- [ ] Ollama + LiteLLM ローカル接続テスト（$0で動くことを確認）
- [ ] コアタスクグラフエンジン（LangGraph）
- [ ] **LAEE基盤: LocalExecutor + ApprovalEngine + AuditLog** ★v0.4
- [ ] **LAEE shell/fs/system ツール実装** ★v0.4
- [ ] KVキャッシュ最適化基盤（安定プレフィックス・append-only）
- [ ] todo.md自動管理
- [ ] コスト追跡（LiteLLM callbacks）
- [ ] 基本UI（タスクリスト + コスト表示）
- [ ] mem0インテグレーション（Semantic Memoryの最小実装）

### Phase 2: Parallel & Planning (Week 3-4)
- [ ] 並列実行エンジン
- [ ] Interactive Planning（Devin式）
- [ ] バックグラウンド計画エージェント（Windsurf式）
- [ ] ツールマスキング状態機械
- [ ] React Flowグラフビジュアライザー
- [ ] **LAEE browser/dev/gui/cron ツール実装** ★v0.4
- [ ] **LAEE UndoManager + リスク評価エンジン** ★v0.4

### Phase 3: Context Bridge & Semantic Memory (Week 5-6) ★v0.3拡張
- [ ] クロスプラットフォームコンテキストブリッジ
- [ ] MCP Server実装
- [ ] Chrome Extension（コンテキスト自動付与）
- [ ] SemanticFingerprint (LSH) 実装
- [ ] ContextZipper（クエリ適応型圧縮）
- [ ] ForgettingCurve + DeltaEncoder実装
- [ ] L1→L4 Memory Hierarchy 完全実装

### Phase 4: Agent CLI Orchestration (Week 7-8) ★v0.3 NEW
- [ ] AgentEngine共通インターフェース定義
- [ ] OpenHands Driver（REST + WebSocket）
- [ ] Claude Code SDK Driver（headless + 並列）
- [ ] Gemini CLI + ADK Driver（Sequential/Parallel/Loop）
- [ ] OpenAI Codex CLI Driver（exec + MCP server mode）
- [ ] AgentCLIRouter（タスク特性→エンジン選択）
- [ ] AGENTS.md / llms-full.txt 知識ファイル管理

### Phase 5: Marketplace & Tools (Week 9-10)
- [ ] 自律ツール発見・インストール
- [ ] MCPツール統合
- [ ] マーケットプレイスUI
- [ ] Ollamaモデル管理UI

### Phase 6: Self-Evolution (Week 11-12)
- [ ] 実行履歴収集・分析
- [ ] プロンプト自動進化（Level 2）
- [ ] モデル選択基準の自動更新
- [ ] エージェントエンジン選択の自動最適化（どのエンジンが得意か学習）
- [ ] 進化レポートダッシュボード

### Phase 7: Unified Cognitive Layer + Meta-Orchestration v2 (Week 13-16)
> 全AIエージェントの記憶・タスク状態・判断を共有する「統合認知層」。A2Aを超え、共有認知へ。
- [ ] UCLドメインモデル（SharedTaskState, Decision, AgentAction, CognitiveMemoryType）
- [ ] Context Adapters（エンジンごとの双方向コンテキスト変換: Claude Code/Gemini/Codex/Ollama/OpenHands/ADK）
- [ ] Insight Extraction Pipeline（実行後の自動知識抽出→UCLメモリ＋タスク状態更新）
- [ ] Agent Affinity Scoring（どのエンジンがこのトピックを最も知っているか）
- [ ] Task Handoff（Agent A → Agent B、判断・成果物・ブロッカー含む完全引き継ぎ）
- [ ] Conflict Resolver（エージェント間の矛盾検出・信頼度重み付き解決）
- [ ] UCL API + CLI + UI
- [ ] クロスエンジン統合テスト＋コンテキスト継続性ベンチマーク

---

## 🛠️ Getting Started

```bash
# 1. Ollamaセットアップ（まず無料で動かす）
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull qwen3:8b

# 2. プロジェクト初期化
git init morphic-agent && cd morphic-agent
uv init
uv add langgraph litellm qdrant-client fastapi instructor redis celery

# 3. フロントエンド
npx create-next-app@latest ui --typescript --tailwind --app
cd ui && npm install reactflow recharts shadcn-ui

# 4. インフラ起動
docker-compose up -d  # PostgreSQL, Redis, Qdrant

# 5. 動作確認（Ollamaで$0タスク実行）
curl -X POST localhost:8000/task \
  -H "Content-Type: application/json" \
  -d '{"goal": "Pythonでフィボナッチ数列を実装", "model": "ollama/qwen3:8b"}'
```

---

## 📝 Claude Code Instructions (実装の鉄則)

**Cursor Agent Prompt 2025-09-03 より採用した鉄則:**
```
1. 「やります」と言ったら即実行。宣言だけして待たない。
2. ユーザーの問題が完全解決するまで実行を止めない。
3. 独立したタスクはデフォルトで並列実行。
4. ツール名をユーザーに見せない。何をしているかを自然言語で説明。
5. 各アクションの前にtodo.mdを読み、後に更新する。
```

**実装優先順位:**
```
Priority 1: ollama_manager.py + llm_router.py（まず$0で動かす）
Priority 2: task_graph/engine.py（コアDAG）
Priority 3: context_engineering/（Manus5原則を最初から実装）
Priority 4: 基本UI（グラフ + コスト表示）
Priority 5: marketplace/auto_discoverer.py
Priority 6: evolution/（データが貯まってから）
```

**禁止事項:**
```
❌ システムプロンプト先頭にタイムスタンプを入れない（KVキャッシュ破壊）
❌ コンテキストを遡って編集しない（append-only原則）
❌ タスク実行中にツール定義を追加/削除しない（マスキングで対応）
❌ API優先でローカルLLMを後回しにしない（LOCAL_FIRST=true）
❌ 計画なしに実行しない（Interactive Planning必須）
```

---

## 📊 Success Metrics (v0.3更新)

| 指標 | Phase 1目標 | 3ヶ月目標 |
|---|---|---|
| タスク成功率 | 70% | 90%+ |
| ローカルLLM使用率 | 60% | 85%+ |
| 平均コスト/タスク | $0.30 | $0.05 |
| KVキャッシュヒット率 | 70% | 90%+ |
| コンテキスト復元精度 | 80% | 95% |
| 進化による改善率 | N/A | +15%/月 |
| Memory圧縮率 | N/A | 10,000→500 tokens (98%) |
| コンテキスト引継ぎ精度 | N/A | 95%+ (マルチAI間) |
| Agent CLI使用率 (OpenHands) | N/A | 長時間タスクの40%+ |
| LAEE ツール実行成功率 | 80% | 95%+ |
| LAEE Undo成功率 | 90% | 98%+ |
| LAEE Audit Log完全性 | 100% | 100% |

---

## 🔒 Safety & Ethics

```
- Tool Sandboxing: 全ツールをDockerコンテナで隔離実行
- Human-in-the-Loop: 破壊的操作は人間確認必須
- Cost Circuit Breaker: 予算95%超過時の強制停止
- Audit Log: 全アクション・LLM呼び出しの完全ログ
- Tool Safety Score: 新ツールインストール前に安全性評価
- Data Privacy: ローカルLLM優先でAPIデータ送信を最小化
- Agent Isolation: 各エージェントエンジンはsandboxed環境で実行
- Memory Privacy: Semantic Memoryのデータはローカル優先

# LAEE Safety Model (v0.4)
- 3-Tier Approval: full-auto / confirm-destructive / confirm-all
- Risk Assessment: 全アクションを5段階(SAFE→CRITICAL)で自動評価
- Audit Trail: .morphic/audit_log.jsonl に全操作を不変ログ
- Undo Stack: 可逆操作はundo可能。rm→ゴミ箱移動で安全削除
- Concurrent Limit: 同時バックグラウンドジョブ数を制限
- Credential Guard: ~/.ssh, ~/.aws, .env 等の読み取りはCRITICALレベル
- User Responsibility: ユーザーが明示的にfull-autoを選択した場合のみ全自動
```

---

## 🌐 Key References

```python
REFERENCES = {
    # ローカルLLM実装参考
    "vibe-local":       "https://github.com/ochyai/vibe-local",
    
    # システムプロンプト分析（116k⭐）
    "system-prompts":   "https://github.com/x1xhlol/system-prompts-and-models-of-ai-tools",
    
    # Manusの文脈工学ブログ（必読）
    "manus-context":    "https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus",
    
    # Agent CLIs (v0.3)
    "openhands":        "https://github.com/OpenHands/OpenHands",
    "openhands-sdk":    "https://github.com/OpenHands/software-agent-sdk",
    "openhands-paper":  "https://arxiv.org/abs/2511.03690",  # V0→V1アーキテクチャ
    "claude-code-sdk":  "https://platform.claude.com/docs/en/agent-sdk/overview",
    "claude-code-headless": "https://code.claude.com/docs/en/headless",
    "gemini-cli":       "https://github.com/google-gemini/gemini-cli",
    "google-adk":       "https://github.com/google/adk-python",
    "adk-docs":         "https://google.github.io/adk-docs/",
    "codex-cli":        "https://github.com/openai/codex",
    "codex-sdk":        "https://developers.openai.com/codex/sdk/",
    "codex-mcp":        "https://developers.openai.com/codex/guides/agents-sdk/",
    
    # Semantic Memory / Context Compression (v0.3)
    "memgpt-letta":     "https://github.com/letta-ai/letta",
    "mem0":             "mem0ai/mem0",
    "titans-paper":     "https://arxiv.org/abs/2501.00663",  # Google Titans
    
    # 主要OSS
    "langgraph":        "langchain-ai/langgraph",
    "litellm":          "BerriAI/litellm",
    "browser-use":      "browser-use/browser-use",
    "qdrant":           "qdrant/qdrant",
    "react-flow":       "xyflow/xyflow",

    # Local Autonomous Execution (v0.4)
    "playwright":       "https://github.com/microsoft/playwright-python",
    "watchdog":         "https://github.com/gorakhargosh/watchdog",
    "apscheduler":      "https://github.com/agronholm/apscheduler",
    "psutil":           "https://github.com/giampaolo/psutil",
}
```

---

*Morphic-Agent — Intelligence that grows with every task.*
*"The boat on the rising tide of model progress, not the pillar stuck to the seabed." — Manus*
*Build date: 2026-04-02 | Version: 0.5.1*

---

> **CHANGELOG v0.4 → v0.5:**
> - **[NEW] Unified Cognitive Layer (UCL)**: 全エージェントの記憶・タスク状態・判断を統合する共有認知層
> - **[NEW] SharedTaskState**: 判断（Decision）・成果物・ブロッカー・エージェント行動履歴をクロスエージェント共有
> - **[NEW] Context Adapters**: エンジンごとの双方向コンテキスト変換（inject/extract）。OSのデバイスドライバ的設計
> - **[NEW] Insight Extraction Pipeline**: 実行後自動知識抽出→UCLメモリ＋タスク状態更新
> - **[NEW] Agent Affinity Scoring**: コンテキスト適合度でルーティング（どのエンジンがこのトピックを最も理解しているか）
> - **[NEW] Task Handoff**: Agent A → Agent B、判断・成果物・ブロッカー含む完全引き継ぎ
> - **[NEW] Conflict Resolver**: エージェント間の矛盾検出・信頼度重み付き解決
> - **[UPDATE] Phase 7を全面再設計**: A2A & Scale → Unified Cognitive Layer + Meta-Orchestration v2（6スプリント）
> - **[UPDATE] 差別化軸追加**: v0.5 共有認知（他フレームワークにない独自性）
>
> **CHANGELOG v0.3 → v0.4:**
> - **[NEW] Local Autonomous Execution Engine (LAEE)**: ローカルPC直接操作。shell/fs/browser/gui/dev/cron 6カテゴリ・40+ツール
> - **[NEW] 3-Tier Approval Mode**: full-auto / confirm-destructive / confirm-all でユーザー自己責任制御
> - **[NEW] Risk Assessment Engine**: 全アクションを5段階(SAFE→CRITICAL)で自動評価
> - **[NEW] Audit Trail**: .morphic/audit_log.jsonl 全操作不変ログ
> - **[NEW] Undo Stack**: 可逆操作のundo機能
> - **[UPDATE] BUILT_IN_TOOLS**: LAEE 40+ツールを追加
> - **[UPDATE] Architecture Diagram**: LAEE層を追加
> - **[UPDATE] Phase 1-2**: LAEE実装タスクを組込み
> - **[UPDATE] Tech Stack**: Playwright, watchdog, APScheduler, psutil追加
>
> **CHANGELOG v0.2 → v0.3:**
> - **[NEW] AI Agent CLI Orchestration**: OpenHands / Claude Code SDK / Gemini CLI+ADK / OpenAI Codex CLIをメタオーケストレーション
> - **[NEW] AgentCLIRouter**: タスク特性×コスト×可用性で最適エンジンを選択
> - **[NEW] Semantic Memory Hierarchy**: L1→L4階層 + LSH Semantic Fingerprint
> - **[NEW] ContextZipper**: クエリ適応型圧縮（10,000→500トークン）
> - **[NEW] ForgettingCurve + DeltaEncoder**: エビングハウス忘却 + Git方式差分
> - **[NEW] AGENTS.md**: Codex CLI向けリポジトリコンテキストファイル追加
> - **[UPDATE] アーキテクチャ図**: Agent CLI Orchestration層を追加
> - **[UPDATE] Phase 4を新設**: Agent CLI Orchestration実装フェーズ
> - **[UPDATE] Phase 7を追加**: A2A & Scale（7フェーズへ拡張）
> - **[UPDATE] 競合差別化**: v0.3メタオーケストレーター軸を追加
>
> **CHANGELOG v0.1 → v0.2:**
> - Ollama/ローカルLLM統合（vibe-local分析結果に基づく）
> - Manus文脈工学5原則の完全組み込み
> - Cursor並列実行鉄則（DEFAULT TO PARALLEL）
> - Windsurf: バックグラウンド計画エージェント + .windsurfrules相当
> - Devin 2.0: Interactive Planning + 自己評価スコア
> - KVキャッシュ設計（最大10倍コスト削減）
> - ツール命名規則でマスキング制御を簡易化
> - ダーク・シックUIテーマ詳細定義
> - 禁止事項リスト追加