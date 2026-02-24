# Morphic-Agent Implementation Plan

> Master implementation plan — 全7フェーズ、14週間
> Phase 1 はスプリント単位の詳細計画、Phase 2-7 は週単位の計画

---

## 設計原則（全フェーズ共通）

```
1. $0で動かすことを最優先に証明する (LOCAL_FIRST)
2. 独立タスクはデフォルト並列 (DEFAULT TO PARALLEL)
3. Context Engineering (Manus 5原則) を Phase 1 から組込む
4. 各フェーズ末に E2E テストで動作を保証する
5. 「宣言したら即実行」— スタブだけ置いて先送りしない
```

---

## 依存関係グラフ

```
[Infrastructure]
  PostgreSQL+pgvector, Redis, Neo4j, Docker Compose
       │
       ▼
[LLM Layer]  ←── Phase 1 最優先
  Ollama Manager → LiteLLM Router → Cost Tracker
       │
       ▼
[Task Graph Engine]  ←── Phase 1 コア
  LangGraph DAG → Scheduler → Parallel Execution
       │
       ├──────────────────────┐
       ▼                      ▼
[Context Engineering]    [Semantic Memory]
  KV-Cache Optimizer      mem0 + pgvector
  Tool State Machine      Neo4j Knowledge Graph
  todo.md Manager         Context Zipper (簡易版)
  Observation Diversifier
       │                      │
       └──────────┬───────────┘
                  ▼
[API Layer]  FastAPI + WebSocket
                  │
                  ▼
[UI Layer]   Next.js 15 + Shadcn/ui
                  │
                  ▼
         *** Phase 1 完了 ***
                  │
       ┌──────────┼──────────┐
       ▼          ▼          ▼
[Phase 2]    [Phase 3]   [Phase 4]
Parallel &   Memory &    Agent CLI
Planning     Context     Orchestration
       │          │          │
       └──────────┼──────────┘
                  ▼
       ┌──────────┼──────────┐
       ▼          ▼          ▼
[Phase 5]    [Phase 6]   [Phase 7]
Marketplace  Evolution   A2A & Scale
```

---

## Phase 1: Foundation (Week 1-2)

> **ゴール**: Ollama で $0 動作する最小エージェントループを完成させる
> **成果物**: ユーザーがゴールを入力 → DAG生成 → Ollama実行 → 結果表示 + コスト$0

### Sprint 1.1: Infrastructure (Day 1-2)

**目標**: Docker Compose 一発でインフラ全起動、DB スキーマ完成

#### 作成ファイル

```
pyproject.toml                          # uv プロジェクト定義
docker-compose.yml                      # PostgreSQL+pgvector, Redis, Neo4j
.env.example                            # 環境変数テンプレート
alembic.ini                             # DB マイグレーション設定
core/__init__.py
core/config.py                          # pydantic-settings ベース設定
core/database.py                        # SQLAlchemy async engine + pgvector
core/models/__init__.py
core/models/base.py                     # SQLAlchemy 宣言的ベースモデル
core/models/task.py                     # Task, SubTask, TaskExecution
core/models/memory.py                   # Memory (with pgvector embedding)
core/models/cost.py                     # CostLog
migrations/env.py                       # Alembic async 環境
migrations/versions/001_initial.py      # 初期スキーマ
```

#### Docker Compose サービス

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16        # pgvector 拡張プリインストール
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
    environment:
      POSTGRES_DB: morphic_agent
      POSTGRES_USER: morphic
      POSTGRES_PASSWORD: morphic_dev

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    # キュー専用。永続化は不要（Phase 1）

  neo4j:
    image: neo4j:5-community
    ports: ["7474:7474", "7687:7687"]    # Browser + Bolt
    environment:
      NEO4J_AUTH: neo4j/morphic_dev
    volumes: [neo4jdata:/data]
```

#### DB スキーマ (PostgreSQL)

```sql
-- tasks: タスクグラフのノード
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',  -- pending|running|success|failed|fallback
    parent_id UUID REFERENCES tasks(id),
    depth INT DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- task_executions: 各タスクの実行記録
CREATE TABLE task_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID REFERENCES tasks(id) NOT NULL,
    model_used VARCHAR(100) NOT NULL,
    prompt_tokens INT,
    completion_tokens INT,
    cost_usd DECIMAL(10,6) DEFAULT 0,
    latency_ms INT,
    result TEXT,
    error TEXT,
    cache_hit BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- memories: セマンティックメモリ (L2 + L4)
CREATE TABLE memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    embedding vector(1536),               -- pgvector
    memory_type VARCHAR(20) NOT NULL,      -- l2_semantic | l4_cold
    access_count INT DEFAULT 1,
    importance_score FLOAT DEFAULT 0.5,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    last_accessed TIMESTAMPTZ DEFAULT now()
);

-- HNSW インデックス (コサイン類似度)
CREATE INDEX ON memories
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- cost_logs: コスト追跡
CREATE TABLE cost_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model VARCHAR(100) NOT NULL,
    prompt_tokens INT DEFAULT 0,
    completion_tokens INT DEFAULT 0,
    cost_usd DECIMAL(10,6) DEFAULT 0,
    cached_tokens INT DEFAULT 0,
    is_local BOOLEAN DEFAULT false,        -- Ollama = true
    created_at TIMESTAMPTZ DEFAULT now()
);
```

#### Neo4j スキーマ (L3 Knowledge Graph)

```cypher
// エンティティノード
CREATE CONSTRAINT entity_name IF NOT EXISTS
  FOR (e:Entity) REQUIRE e.name IS UNIQUE;

// 関係タイプ: RELATES_TO, DEPENDS_ON, PART_OF, CREATED_BY, etc.
// Phase 1 は動的ラベルで柔軟に運用
```

#### 完了条件

- [ ] `docker compose up -d` で 3 サービス全起動
- [ ] `alembic upgrade head` でスキーマ作成成功
- [ ] pgvector の `vector` 型でインサート・検索テスト通過
- [ ] Neo4j に Cypher クエリでノード作成・検索テスト通過
- [ ] `core/config.py` で `.env` 読み込み + pydantic validation

---

### Sprint 1.2: LLM Layer (Day 3-4)

**目標**: Ollama でローカル推論が $0 で動作、コスト追跡が機能

#### 作成ファイル

```
core/llm_router/__init__.py
core/llm_router/router.py              # MultiLLMRouter (LiteLLM統合)
core/llm_router/ollama_manager.py       # OllamaManager
core/llm_router/cost_tracker.py         # CostTracker (callback ベース)
core/llm_router/models.py              # LLMResponse, ModelTier, TaskType
tests/test_llm_router.py
tests/test_ollama_manager.py
```

#### OllamaManager 仕様

```python
class OllamaManager:
    """Ollama ライフサイクル管理"""
    base_url: str = "http://127.0.0.1:11434"

    async def is_running(self) -> bool:
        """GET /api/tags でヘルスチェック"""

    async def list_models(self) -> list[str]:
        """インストール済みモデル一覧"""

    async def pull_model(self, model: str) -> None:
        """POST /api/pull でモデル取得"""

    async def ensure_model(self, model: str) -> bool:
        """モデルが無ければ pull、あれば True"""

    def get_recommended_model(self, ram_gb: int) -> str:
        """マシンスペックに応じた推奨モデルを返す
        8GB  → qwen3:8b
        16GB → qwen3:8b (default)
        32GB → qwen3-coder:30b
        GPU  → llama3.3:70b
        """
```

#### MultiLLMRouter 仕様

```python
class MultiLLMRouter:
    MODEL_TIERS = {
        "free":   ["ollama/qwen3:8b", "ollama/deepseek-r1:8b", ...],
        "low":    ["claude-haiku-4-5-20251001", "gemini/gemini-2.0-flash"],
        "medium": ["claude-sonnet-4-6", "gpt-4o-mini", ...],
        "high":   ["claude-opus-4-6", "gpt-4o"],
    }

    TASK_MODEL_MAP = {
        "simple_qa":        ("free", "low"),
        "code_generation":  ("free", "medium"),
        "complex_reasoning":("medium", "high"),
        "file_operation":   ("free", "low"),
        "long_context":     ("medium",),
    }

    async def route(self, task_type: str, budget_remaining: float) -> str:
        """タスク種別と残予算から最適モデルを選択"""
        # 1. LOCAL_FIRST: Ollama が動いていれば free tier 優先
        # 2. 予算チェック: budget_remaining < threshold → 強制 free
        # 3. タスク種別 → tier → 利用可能な最初のモデル

    async def call(self, model: str, messages: list, **kwargs) -> LLMResponse:
        """LiteLLM completion() ラッパー"""
        # cache={"type": "disk"} でディスクキャッシュ有効化
        # Ollama の場合 api_base を差し替え
```

#### CostTracker 仕様

```python
class CostTracker:
    """LiteLLM success_callback ベースのリアルタイムコスト追跡"""

    async def on_success(self, kwargs, response, start_time, end_time):
        """LiteLLM callback: 全LLM呼び出しのコストをDB記録"""

    async def get_daily_total(self) -> float:
        """本日のAPI支出合計"""

    async def get_monthly_total(self) -> float:
        """今月のAPI支出合計"""

    async def get_local_usage_rate(self) -> float:
        """ローカルLLM使用率 (回数ベース)"""

    def check_budget(self, budget_usd: float) -> bool:
        """予算超過チェック。True=余裕あり"""

    async def get_savings_from_local(self) -> float:
        """ローカルLLMで節約できた推定額"""
```

#### 完了条件

- [ ] Ollama で `qwen3:8b` に推論リクエスト → レスポンス取得
- [ ] LiteLLM 経由で Ollama 呼び出し → `cost_logs` に記録 (cost=0)
- [ ] API キー設定時に Claude Haiku 呼び出し → `cost_logs` に記録 (cost>0)
- [ ] `get_local_usage_rate()` が正確な比率を返す
- [ ] 予算超過時にルーターが強制的に free tier を返す

---

### Sprint 1.3: Task Graph Engine (Day 5-7)

**目標**: ゴール入力 → LLM で分解 → DAG 生成 → 実行 → 結果

#### 作成ファイル

```
core/task_graph/__init__.py
core/task_graph/engine.py               # TaskGraphEngine (LangGraph)
core/task_graph/models.py               # AgentState, TaskNode
core/task_graph/scheduler.py            # TaskScheduler (並列実行)
core/task_graph/intent_analyzer.py      # IntentAnalyzer (ゴール → サブタスク分解)
tests/test_task_graph.py
```

#### AgentState モデル

```python
class AgentState(TypedDict):
    goal: str                              # ユーザーの元ゴール
    tasks: list[TaskNode]                  # サブタスク一覧
    current_task_index: int                # 現在実行中のタスク
    history: Annotated[list[dict], add]    # append-only 実行履歴
    context: str                           # 圧縮済みコンテキスト
    status: str                            # overall status
    cost_so_far: float                     # 累計コスト

class TaskNode(BaseModel):
    id: str
    description: str
    status: str = "pending"                # pending|running|success|failed
    dependencies: list[str] = []           # 先行タスクID
    result: str | None = None
    error: str | None = None
    model_used: str | None = None
    cost_usd: float = 0.0
```

#### TaskGraphEngine 仕様

```python
class TaskGraphEngine:
    def build_graph(self) -> StateGraph:
        """LangGraph StateGraph を構築"""
        graph = StateGraph(AgentState)
        graph.add_node("analyze_intent",   self.analyze_intent)
        graph.add_node("plan_tasks",       self.plan_tasks)
        graph.add_node("execute_task",     self.execute_task)
        graph.add_node("observe_result",   self.observe_result)
        graph.add_node("handle_failure",   self.handle_failure)
        graph.add_node("complete",         self.complete)

        graph.set_entry_point("analyze_intent")
        graph.add_edge("analyze_intent", "plan_tasks")
        graph.add_edge("plan_tasks", "execute_task")

        graph.add_conditional_edges(
            "execute_task",
            self.route_after_execution,
            {
                "success":  "observe_result",
                "failure":  "handle_failure",
            }
        )

        graph.add_conditional_edges(
            "observe_result",
            self.has_next_task,
            {
                "continue": "execute_task",
                "done":     "complete",
            }
        )

        graph.add_conditional_edges(
            "handle_failure",
            self.failure_strategy,
            {
                "retry":    "execute_task",   # リトライ (max 2回)
                "fallback": "execute_task",   # 別モデルで再試行
                "abort":    "complete",       # 諦め
            }
        )

        graph.add_edge("complete", END)
        return graph.compile()

    async def run(self, goal: str) -> AgentState:
        """ゴールを受け取り、DAG全体を実行して最終状態を返す"""
```

#### IntentAnalyzer 仕様

```python
class IntentAnalyzer:
    """ユーザーのゴールをサブタスクに分解する"""

    DECOMPOSE_PROMPT = """
    あなたはタスク分解の専門家です。
    ユーザーのゴールを、実行可能な具体的なサブタスクに分解してください。

    ルール:
    - 各サブタスクは独立して実行可能にする
    - 依存関係がある場合は明示する
    - 並列実行可能なタスクはそのように記述する

    出力形式 (JSON):
    {
      "tasks": [
        {"id": "t1", "description": "...", "dependencies": []},
        {"id": "t2", "description": "...", "dependencies": ["t1"]},
        ...
      ]
    }
    """

    async def analyze(self, goal: str) -> list[TaskNode]:
        """LLM でゴールをサブタスクに分解"""
```

#### TaskScheduler 仕様

```python
class TaskScheduler:
    """独立タスクを並列実行、依存タスクを順次実行"""

    def get_ready_tasks(self, tasks: list[TaskNode]) -> list[TaskNode]:
        """依存がすべて完了しているタスクを返す"""

    async def execute_parallel(self, tasks: list[TaskNode]) -> list[TaskNode]:
        """独立タスクを asyncio.gather で並列実行"""
```

#### 完了条件

- [ ] "Pythonでフィボナッチ数列を実装" → サブタスク分解 → 各サブタスク実行 → 結果取得
- [ ] 失敗時のフォールバック: Ollama 失敗 → 別モデルで再試行
- [ ] 並列実行: 独立サブタスク2つを同時実行、順次より速いことを確認
- [ ] `tasks` テーブルに全タスクが記録されている
- [ ] `task_executions` に各実行の詳細が記録されている

---

### Sprint 1.3b: Local Autonomous Execution Engine — LAEE (Day 8-9) ★v0.4 NEW

**目標**: エージェントがローカルPCを直接操作する実行レイヤーの基盤実装

#### 作成ファイル

```
core/local_execution/__init__.py
core/local_execution/executor.py            # LocalExecutor 中核
core/local_execution/approval_engine.py      # 3段階承認モード
core/local_execution/audit_log.py           # 全操作不変ログ (JSONL)
core/local_execution/risk_assessor.py       # アクションリスク評価
core/local_execution/undo_manager.py        # 可逆操作のundo管理
core/local_execution/tools/__init__.py
core/local_execution/tools/shell_tools.py    # shell_exec/background/stream/pipe
core/local_execution/tools/fs_tools.py       # fs_read/write/edit/delete/move/glob/watch/tree
core/local_execution/tools/system_tools.py   # system_process/resource/clipboard/notify/screenshot
core/local_execution/tools/dev_tools.py      # dev_git/docker/pkg_install/env_setup
tests/test_local_execution.py
tests/test_approval_engine.py
```

#### ApprovalEngine 仕様

```python
class ApprovalEngine:
    """3段階承認モード × 5段階リスクレベルのマトリクスで実行可否を判定"""

    class ApprovalMode(Enum):
        FULL_AUTO = "full-auto"                    # 全自動（ユーザー自己責任）
        CONFIRM_DESTRUCTIVE = "confirm-destructive" # 破壊的操作のみ確認
        CONFIRM_ALL = "confirm-all"                # 全操作確認

    class RiskLevel(Enum):
        SAFE = 0      # 読み取り専用（ls, cat, ps）
        LOW = 1       # 可逆的作成（mkdir, touch, open）
        MEDIUM = 2    # 変更（edit, brew install）
        HIGH = 3      # 削除・終了（rm, kill, config変更）
        CRITICAL = 4  # 再帰削除・sudo・認証情報

    async def check(self, action: Action, mode: ApprovalMode) -> bool:
        """承認マトリクスに基づき自動承認 or ユーザー確認"""

    def assess_risk(self, tool: str, args: dict) -> RiskLevel:
        """ツール名+引数からリスクレベルを自動判定
        例: fs_delete + recursive=True → CRITICAL
            shell_exec + 'sudo' in cmd → CRITICAL
            fs_read → SAFE
        """
```

#### LocalExecutor 仕様

```python
class LocalExecutor:
    """タスクグラフのexecute_taskノードから呼ばれる実行エンジン"""

    async def execute(self, action: Action) -> Observation:
        """リスク評価→承認→スナップショット→実行→ログの5ステップ"""

    async def undo_last(self) -> Observation:
        """直前の可逆操作をundo"""

    async def run_tool(self, tool_name: str, args: dict) -> str:
        """ツールディスパッチャー。tool_nameからツール関数を解決して実行"""
```

#### ShellTools 仕様

```python
class ShellTools:
    async def shell_exec(self, cmd: str, cwd: str = None, timeout: int = 120) -> str:
        """コマンド同期実行。stdout+stderrを返す"""

    async def shell_background(self, cmd: str) -> str:
        """バックグラウンドジョブ起動。ジョブIDを返す"""

    async def shell_stream(self, cmd: str) -> AsyncIterator[str]:
        """stdout/stderrをリアルタイムストリーム"""

    async def shell_pipe(self, commands: list[str]) -> str:
        """パイプライン構築・実行 (cmd1 | cmd2 | cmd3)"""
```

#### FSTools 仕様

```python
class FSTools:
    async def fs_read(self, path: str, encoding: str = "utf-8") -> str:
    async def fs_write(self, path: str, content: str) -> str:
    async def fs_edit(self, path: str, old: str, new: str) -> str:
    async def fs_delete(self, path: str, recursive: bool = False) -> str:
        """recursive=True は CRITICAL リスク。undo時はゴミ箱移動"""
    async def fs_move(self, src: str, dst: str) -> str:
    async def fs_glob(self, pattern: str, path: str = ".") -> list[str]:
    async def fs_watch(self, path: str, callback: Callable) -> str:
        """watchdogでファイル変更監視"""
    async def fs_tree(self, path: str, depth: int = 3) -> str:
```

#### AuditLog 仕様

```python
class AuditLog:
    """全操作の不変ログ。append-only JSONL。"""
    LOG_PATH = ".morphic/audit_log.jsonl"

    def log(self, action: Action, result: str, risk: RiskLevel, success: bool):
        """アクション・結果・リスク・成否をJSONLに追記"""

    def query(self, tool: str = None, risk: str = None, since: datetime = None) -> list:
        """監査ログ検索"""

    def get_stats(self) -> dict:
        """ツール別/リスク別の実行統計"""
```

#### 完了条件

- [ ] `shell_exec("echo hello")` → "hello" が返る
- [ ] `fs_write` + `fs_read` で書き込み・読み取りの往復テスト
- [ ] `fs_delete(recursive=True)` が `confirm-destructive` モードでユーザー確認を要求
- [ ] `full-auto` モードで全操作が確認なしに実行される
- [ ] `confirm-all` モードで SAFE 以外の全操作がユーザー確認を要求
- [ ] 全操作が `.morphic/audit_log.jsonl` にログ記録される
- [ ] `undo_last()` で `fs_write` の操作が元に戻る
- [ ] `sudo` を含むコマンドが自動的に CRITICAL レベルに評価される

---

### Sprint 1.4: Context Engineering (Day 10-11)

**目標**: Manus 5原則の基盤実装。KV-Cache最適化 + ツールマスキング + todo.md

#### 作成ファイル

```
core/context_engineering/__init__.py
core/context_engineering/kv_cache_optimizer.py
core/context_engineering/tool_state_machine.py
core/context_engineering/todo_manager.py
core/context_engineering/observation_diversifier.py
core/context_engineering/file_context.py
tests/test_context_engineering.py
```

#### 各モジュール仕様

**kv_cache_optimizer.py — 原則1: KV-Cache を設計の中心に**

```python
class KVCacheOptimizer:
    STABLE_PREFIX: str  # 不変のシステムプロンプト先頭部分

    def build_system_prompt(self, dynamic_context: dict) -> str:
        """安定プレフィックス + 動的セクション（末尾）の結合
        先頭は絶対に変えない → KV-Cache を最大化"""

    def serialize_context(self, context: dict) -> str:
        """JSON sort_keys=True で決定論的シリアライズ"""

    def append_to_history(self, history: list, new_entry: dict) -> list:
        """append-only。過去のエントリを編集しない"""
```

**tool_state_machine.py — 原則2: ツールはマスクする**

```python
class ToolStateMachine:
    """全ツール定義を常に保持。状態に応じて使用可否をマスク"""

    ALL_TOOLS: list[ToolDef]  # 全ツール定義 (不変)

    def get_allowed_tools(self, state: AgentState) -> list[ToolDef]:
        """現在の状態で使用可能なツールだけを返す
        ただしツール定義自体は常にプロンプトに含める"""

    def mask(self, tool_name: str, reason: str) -> None:
        """ツールを一時的に無効化（定義は残す）"""

    def unmask(self, tool_name: str) -> None:
        """ツールを再有効化"""
```

**todo_manager.py — 原則4: todo.md でアテンション操作**

```python
class TodoManager:
    TODO_PATH = "todo.md"

    async def read(self) -> str:
        """各イテレーション先頭で読む"""

    async def update(self, tasks: list[TaskNode]) -> None:
        """各イテレーション末尾で更新"""

    def format_for_context(self, todo_content: str) -> str:
        """LLMコンテキストに注入するフォーマット
        [IN PROGRESS] タスクを強調して先頭・末尾のアテンションを活用"""
```

**observation_diversifier.py — 原則5: 観察の多様性**

```python
class ObservationDiversifier:
    TEMPLATES = [
        "Result: {result}\nStatus: {status}",
        "Observation #{n}: {result} [{status}]",
        "Completed: {result} | State: {status}",
    ]

    def serialize(self, obs: dict, n: int) -> str:
        """テンプレートローテーションで類似観察のドリフトを防止"""
```

**file_context.py — 原則3: ファイルシステムを無限コンテキストに**

```python
class FileContext:
    CACHE_DIR = ".morphic/context_cache"

    def save(self, key: str, content: str) -> str:
        """コンテンツをファイル保存し、参照トークンを返す"""

    def load(self, key: str) -> str:
        """キーからコンテンツを復元"""

    def compress_webpage(self, url: str, content: str) -> str:
        """Webページをキャッシュし、URLリファレンスだけ返す"""
```

#### 完了条件

- [ ] システムプロンプトの先頭128トークンが常に同一（キャッシュ検証）
- [ ] ツール定義数が実行中に変動しないことをアサート
- [ ] todo.md がタスク実行前後で自動更新される
- [ ] 3連続の類似観察がすべて異なるフォーマットでシリアライズされる

---

### Sprint 1.5: Semantic Memory (Day 12-13)

**目標**: L1-L4 メモリ階層の基盤実装。mem0 + pgvector + Neo4j 連携

#### 作成ファイル

```
core/semantic_memory/__init__.py
core/semantic_memory/memory_hierarchy.py    # L1-L4 統合管理
core/semantic_memory/knowledge_graph.py     # Neo4j L3 ラッパー
core/semantic_memory/context_zipper.py      # 簡易版圧縮
tests/test_memory.py
```

#### MemoryHierarchy 仕様

```python
class MemoryHierarchy:
    """CPU キャッシュ階層と同じ設計思想"""

    # L1: Active Context (in-memory, ~2000 tokens)
    l1_buffer: list[dict]  # 直近N発言をraw保持

    # L2: Semantic Cache (mem0 + pgvector)
    l2_mem0: Memory  # mem0.Memory()

    # L3: Structured Facts (Neo4j)
    l3_graph: KnowledgeGraph

    # L4: Cold Storage (PostgreSQL memories table)
    l4_store: AsyncSession

    async def add(self, content: str, role: str = "user") -> None:
        """新しい発言を各層に非同期で振り分け"""
        # L1: バッファに追加 (容量超過で古いものを L2 に降格)
        # L2: mem0 で自動ファクト抽出 + pgvector 保存
        # L3: エンティティ抽出 → Neo4j に保存
        # L4: 生テキスト全保存

    async def retrieve(self, query: str, max_tokens: int = 500) -> str:
        """クエリに関連する記憶を階層的に検索"""
        # L1 → L2 → L3 → L4 の順で検索
        # max_tokens 予算内に収まるよう優先度でトリム
```

#### KnowledgeGraph 仕様 (Neo4j)

```python
class KnowledgeGraph:
    """L3: エンティティ・関係の構造化ストア"""

    async def add_entity(self, name: str, entity_type: str, properties: dict) -> None:
        """CREATE (e:Entity {name: $name, type: $type, ...})"""

    async def add_relation(self, from_name: str, relation: str, to_name: str) -> None:
        """MATCH (a), (b) CREATE (a)-[:REL {type: $rel}]->(b)"""

    async def query(self, entity_names: list[str], depth: int = 2) -> list[dict]:
        """エンティティから depth ホップ以内の関連ノード・関係を返す"""

    async def extract_and_store(self, text: str) -> None:
        """テキストから LLM でエンティティ・関係を抽出して保存"""
```

#### SimplifiedContextZipper 仕様

```python
class ContextZipper:
    """Phase 1 簡易版: L2 検索 + L3 Facts をトークン予算内に収める"""

    async def compress(
        self,
        conversation_history: list[dict],
        current_query: str,
        target_tokens: int = 500
    ) -> str:
        """クエリに最適化した圧縮コンテキストを動的生成
        Phase 3 で LSH + ForgettingCurve + DeltaEncoder に拡張"""
```

#### 完了条件

- [ ] 会話を add() → retrieve() で関連記憶が返る
- [ ] mem0 が pgvector にベクトル保存していることを確認
- [ ] Neo4j にエンティティ・関係が保存され、Cypher で検索可能
- [ ] ContextZipper で 5000 トークンの履歴 → 500 トークンに圧縮

---

### Sprint 1.6: API + UI (Day 14-15)

**目標**: FastAPI バックエンド + Next.js 最小UI

#### 作成ファイル (バックエンド)

```
api/__init__.py
api/main.py                             # FastAPI app factory
api/deps.py                             # 依存性注入 (DB session, router, etc.)
api/routes/__init__.py
api/routes/tasks.py                     # POST/GET /api/tasks
api/routes/models.py                    # GET /api/models
api/routes/cost.py                      # GET /api/cost
api/routes/memory.py                    # GET /api/memory/search
api/websocket.py                        # WebSocket /ws/tasks/{id}
```

#### API エンドポイント

```
POST   /api/tasks              タスク作成 (goal を受け取り DAG 生成・実行開始)
GET    /api/tasks              タスク一覧 (status フィルタ対応)
GET    /api/tasks/{id}         タスク詳細 (サブタスク・実行ログ含む)
DELETE /api/tasks/{id}         タスクキャンセル

GET    /api/models             利用可能モデル一覧 (Ollama + API)
GET    /api/models/status      Ollama ヘルスチェック

GET    /api/cost               コストサマリー (日次/月次/ローカル率)
GET    /api/cost/logs          コストログ一覧

GET    /api/memory/search?q=   セマンティック記憶検索

WS     /ws/tasks/{id}          タスク実行のリアルタイム進捗
```

#### 作成ファイル (フロントエンド)

```
ui/                                     # npx create-next-app@latest
ui/app/layout.tsx                       # ダークテーマ ルートレイアウト
ui/app/page.tsx                         # ダッシュボード (タスク一覧 + コスト)
ui/app/tasks/[id]/page.tsx              # タスク詳細ページ
ui/components/TaskList.tsx              # タスク一覧コンポーネント
ui/components/TaskDetail.tsx            # タスク詳細 (サブタスク表示)
ui/components/CostMeter.tsx             # コスト表示 (予算バー + ローカル率)
ui/components/ModelStatus.tsx           # Ollama 状態表示
ui/components/GoalInput.tsx             # ゴール入力フォーム
ui/lib/api.ts                           # API クライアント
ui/lib/theme.ts                         # morphicAgentTheme 定義
```

#### UI Phase 1 スコープ

```
┌─────────────────────────────────────────────────┐
│ Morphic-Agent                          [Models] │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌─ Goal Input ──────────────────────────────┐  │
│  │ [テキストエリア: ゴールを入力]    [実行]  │  │
│  └───────────────────────────────────────────┘  │
│                                                 │
│  ┌─ Active Tasks ─────────────────────────────┐ │
│  │ ● "フィボナッチ実装"  [Running] qwen3:8b   │ │
│  │   ├ ✓ アルゴリズム設計                     │ │
│  │   ├ ⚡ コード実装 [Running]                │ │
│  │   └ ○ テスト作成 [Pending]                 │ │
│  └────────────────────────────────────────────┘ │
│                                                 │
│  ┌─ Cost ──────────────┐  ┌─ Model Status ──┐  │
│  │ Today:    $0.00     │  │ Ollama: ● ON    │  │
│  │ Local:    100%      │  │ qwen3:8b ✓      │  │
│  │ Budget:   ████░ 95% │  │ API Keys: 0     │  │
│  └─────────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────┘
```

#### 完了条件

- [ ] `POST /api/tasks` でゴール送信 → タスク実行開始
- [ ] WebSocket でリアルタイム進捗受信
- [ ] Next.js UI でタスク一覧・詳細表示
- [ ] コストメーター表示（$0 / Local 100%）

---

### Sprint 1.7: Integration & E2E Test (Day 16)

**目標**: 全コンポーネント結合テスト。$0 パス検証。

#### テストシナリオ

```
E2E Test 1: $0 完全ローカルパス
  Input:  "Pythonでフィボナッチ数列を実装して"
  Flow:   Intent Analysis (Ollama) → DAG生成 → 実行 (Ollama) → 結果
  Assert: cost_usd == 0, task.status == "success", result contains "fibonacci"

E2E Test 2: 失敗リカバリー
  Input:  意図的に失敗させるタスク
  Flow:   実行 → 失敗 → フォールバック → 成功
  Assert: task_executions に retry 記録、最終 status == "success"

E2E Test 3: 並列実行
  Input:  "AとBを同時に実行して"
  Flow:   独立サブタスク2つを asyncio.gather で並列
  Assert: 2タスクの開始時刻がほぼ同一 (差 < 1秒)

E2E Test 4: メモリ永続化
  Input:  タスク実行 → 別セッションで関連質問
  Flow:   add() → retrieve() で前回の文脈が返る
  Assert: retrieved_context にタスク結果の情報が含まれる

E2E Test 5: LAEE ローカル実行 (v0.4)
  Input:  "testディレクトリを作成してPythonファイルを3つ生成して"
  Flow:   fs_write × 3 (並列) → fs_tree → 結果確認
  Assert: ファイルが実際に作成されている, audit_log.jsonl に記録あり

E2E Test 6: LAEE 承認モードテスト (v0.4)
  Input:  confirm-destructive モードで fs_delete(recursive=True)
  Flow:   リスク評価 → CRITICAL → ユーザー確認要求
  Assert: ユーザー確認なしでは実行されない

E2E Test 7: LAEE Undo テスト (v0.4)
  Input:  fs_write("test.txt") → undo_last()
  Flow:   ファイル作成 → undo → ファイル削除
  Assert: test.txt が存在しない
```

#### 完了条件

- [ ] E2E Test 1-4 全パス
- [ ] `docker compose up -d` → `uv run pytest` で全テスト通過
- [ ] UI でタスク実行 → 結果表示の一連フロー動作確認

---

## Phase 1 完了時の成果物サマリー

```
作成ファイル数: ~60 ファイル (LAEE +15)
Python パッケージ:
  langgraph, litellm, sqlalchemy[asyncio], asyncpg, pgvector,
  neo4j, mem0ai, fastapi, uvicorn, pydantic-settings,
  celery[redis], instructor, alembic, httpx, pytest, pytest-asyncio,
  playwright, watchdog, apscheduler, psutil  # LAEE v0.4

Next.js パッケージ:
  next, react, tailwindcss, shadcn-ui (初期), recharts

Docker Compose サービス:
  PostgreSQL 16 + pgvector, Redis 7, Neo4j 5

動作確認:
  ユーザーがゴール入力 → DAG生成 → Ollama実行 → 結果表示
  コスト: $0 (全ローカル実行)
```

---

## Phase 2: Parallel & Planning (Week 3-4)

> **ゴール**: 並列実行の本格化 + Interactive Planning で品質・速度向上

### Week 3: 並列実行 & Interactive Planning

| # | 実装項目 | ファイル | 依存 |
|---|---|---|---|
| 2.1 | ParallelExecutionEngine 本格実装 | `core/task_graph/parallel.py` | Phase 1 DAG |
| 2.2 | Celery ワーカー統合 | `core/task_graph/celery_worker.py` | Redis |
| 2.3 | Interactive Planning System | `core/planning/interactive_planner.py` | DAG + LLM Router |
| 2.4 | コスト見積もりエンジン | `core/planning/cost_estimator.py` | Cost Tracker |

**Interactive Planning フロー:**
```
1. ユーザーがゴール入力
2. LLM がサブタスク分解 + 使用モデル提案
3. コスト見積もり計算
4. 計画 + 見積もりをUIで提示
5. ユーザーが [承認 / 編集 / 拒否]
6. 承認後に実行開始
```

### Week 4: Background Planner & Graph Visualization

| # | 実装項目 | ファイル | 依存 |
|---|---|---|---|
| 2.5 | Background Planner (Windsurf式) | `core/planning/background_planner.py` | Planning |
| 2.6 | Tool State Machine 強化 | `core/context_engineering/tool_state_machine.py` | Phase 1 |
| 2.7 | React Flow タスクグラフUI | `ui/components/TaskGraph.tsx` | React Flow |
| 2.8 | Planning View UI | `ui/components/PlanningView.tsx` | Phase 1 UI |
| 2.9 | LAEE Browser Tools (Playwright) | `core/local_execution/tools/browser_tools.py` | LAEE基盤 |
| 2.10 | LAEE GUI Tools (macOS) | `core/local_execution/tools/gui_tools.py` | LAEE基盤 |
| 2.11 | LAEE Cron Tools (APScheduler) | `core/local_execution/tools/cron_tools.py` | LAEE基盤 |
| 2.12 | LAEE UndoManager + RiskAssessor強化 | `core/local_execution/undo_manager.py` | LAEE基盤 |

**Phase 2 完了条件:**
- [ ] 3つの独立タスクが並列実行され、順次比3倍以上高速
- [ ] Interactive Planning で計画提示 → ユーザー承認 → 実行
- [ ] React Flow でDAGがリアルタイム可視化される
- [ ] Background Planner が実行中に計画を継続改善

---

## Phase 3: Context Bridge & Semantic Memory (Week 5-6)

> **ゴール**: 記憶と文脈を研究グレードに引き上げ + クロスプラットフォーム対応

### Week 5: Semantic Memory 本格実装

| # | 実装項目 | ファイル |
|---|---|---|
| 3.1 | SemanticFingerprint (LSH) | `core/semantic_memory/semantic_fingerprint.py` |
| 3.2 | ContextZipper 完全版 | `core/semantic_memory/context_zipper.py` |
| 3.3 | ForgettingCurve | `core/semantic_memory/forgetting_curve.py` |
| 3.4 | DeltaEncoder | `core/semantic_memory/delta_encoder.py` |
| 3.5 | HierarchicalSummarizer | `core/semantic_memory/hierarchical_summary.py` |

### Week 6: Context Bridge & MCP

| # | 実装項目 | ファイル |
|---|---|---|
| 3.6 | Cross-Platform Context Bridge | `core/memory/context_bridge.py` |
| 3.7 | MCP Server 実装 | `integrations/mcp/server.py` |
| 3.8 | MCP Client 実装 | `integrations/mcp/client.py` |
| 3.9 | Chrome Extension | `integrations/browser_extension/` |
| 3.10 | L1→L4 統合テスト | `tests/test_memory_hierarchy.py` |

**Phase 3 完了条件:**
- [ ] 10,000 トークン → 500 トークンに圧縮 (情報保持率 > 90%)
- [ ] LSH で意味的に近い記憶を O(1) に近い速度で取得
- [ ] MCP Server として他ツールから Morphic-Agent の記憶にアクセス可能
- [ ] 忘却曲線で古い低重要度記憶が自動的に L3 へ昇格・L2 から削除

---

## Phase 4: Agent CLI Orchestration (Week 7-8)

> **ゴール**: メタオーケストレーターとして 4 つの Agent CLI を統合管理

### Week 7: 共通インターフェース + OpenHands & Claude Code

| # | 実装項目 | ファイル |
|---|---|---|
| 4.1 | AgentEngine Protocol | `core/agent_orchestration/agent_engine_protocol.py` |
| 4.2 | OpenHands Driver | `core/agent_orchestration/openhands_driver.py` |
| 4.3 | Claude Code SDK Driver | `core/agent_orchestration/claude_code_driver.py` |
| 4.4 | AgentCLIRouter 基盤 | `core/agent_orchestration/agent_cli_router.py` |

### Week 8: Gemini & Codex + ルーター完成

| # | 実装項目 | ファイル |
|---|---|---|
| 4.5 | Gemini CLI + ADK Driver | `core/agent_orchestration/gemini_adk_driver.py` |
| 4.6 | Codex CLI Driver | `core/agent_orchestration/codex_cli_driver.py` |
| 4.7 | AgentCLIRouter ルーティング完成 | (4.4 拡張) |
| 4.8 | 知識ファイル管理 | `core/agent_orchestration/knowledge_files.py` |

**Phase 4 完了条件:**
- [ ] 同一タスクを OpenHands / Claude Code / Gemini / Codex で実行し結果比較
- [ ] AgentCLIRouter がタスク特性に応じて最適エンジンを自動選択
- [ ] 各エンジンの可用性チェック + フォールバック

---

## Phase 5: Marketplace & Tools (Week 9-10)

> **ゴール**: ツール自律発見・インストール・共有

| # | 実装項目 | ファイル |
|---|---|---|
| 5.1 | Auto Tool Discoverer | `marketplace/discovery/auto_discoverer.py` |
| 5.2 | MCP Registry 検索 | `marketplace/discovery/mcp_search.py` |
| 5.3 | Tool Installer | `marketplace/installer/tool_installer.py` |
| 5.4 | Ollama Model Manager | `marketplace/installer/ollama_installer.py` |
| 5.5 | Tool Safety Scorer | `marketplace/registry/safety_scorer.py` |
| 5.6 | Marketplace UI | `ui/app/marketplace/page.tsx` |

**Phase 5 完了条件:**
- [ ] タスク失敗時に必要ツールを自動検索・提案
- [ ] MCP Registry から 1-click インストール
- [ ] Ollama モデルの UI 管理 (pull/delete/switch)
- [ ] ツール安全性スコア表示

---

## Phase 6: Self-Evolution (Week 11-12)

> **ゴール**: 実行データから自律改善

| # | 実装項目 | ファイル |
|---|---|---|
| 6.1 | Execution Analyzer | `core/evolution/execution_analyzer.py` |
| 6.2 | Tactical Recovery (Level 1) | `core/evolution/tactical_recovery.py` |
| 6.3 | Strategy Updater (Level 2) | `core/evolution/strategy_updater.py` |
| 6.4 | Systemic Evolver (Level 3) | `core/evolution/systemic_evolver.py` |
| 6.5 | Evolution Dashboard | `ui/app/evolution/page.tsx` |

**Phase 6 完了条件:**
- [ ] 失敗パターン分析 → プロンプトテンプレート自動改善
- [ ] モデル選択精度が 2 週間で +10% 改善
- [ ] Agent CLI エンジン選択の自動最適化
- [ ] 進化レポートが UI で閲覧可能

---

## Phase 7: A2A & Scale (Week 13-14)

> **ゴール**: マルチエージェント協調 + ベンチマーク

| # | 実装項目 | ファイル |
|---|---|---|
| 7.1 | A2A Protocol 実装 | `agents/a2a/protocol.py` |
| 7.2 | Agent Coordinator | `agents/a2a/coordinator.py` |
| 7.3 | Multi-Agent Parallel | `agents/a2a/parallel.py` |
| 7.4 | Benchmark Suite | `benchmarks/` |
| 7.5 | vs Manus / Devin / OpenHands 比較 | `benchmarks/results/` |

**Phase 7 完了条件:**
- [ ] 3 エージェントが A2A で協調してタスク完了
- [ ] SWE-bench lite でスコア計測
- [ ] ベンチマーク結果ダッシュボード

---

## リスク管理

| リスク | 影響度 | 発生確率 | 緩和策 |
|---|---|---|---|
| LangGraph の破壊的変更 | 高 | 低 | 薄いラッパーで API 隔離 |
| Ollama モデル品質不足 | 中 | 中 | タスク種別で API フォールバック自動化 |
| Neo4j Community の制約 | 低 | 低 | Phase 1 規模では問題なし |
| Agent CLI (OpenHands等) の API 変更 | 中 | 中 | AgentEngine Protocol で抽象化 |
| Phase 1 が 2 週超過 | 高 | 中 | UI を最低限に絞り、API 優先 |
| mem0 の pgvector 互換性 | 低 | 低 | 直接 pgvector 使用にフォールバック可能 |

---

## クリティカルパス

```
Sprint 1.1 (Infra)
    → Sprint 1.2 (LLM Layer) ← 最優先。ここが遅れると全体遅延
        → Sprint 1.3 (Task Graph) ← コア。Phase 2-7 の全てが依存
            → Sprint 1.3b (LAEE) ← 1.3 と部分並列可能。実行レイヤー ★v0.4
            → Sprint 1.4 (Context Eng.) ← 1.3 と部分並列可能
            → Sprint 1.5 (Memory) ← 1.3 と部分並列可能
                → Sprint 1.6 (API + UI) ← 1.3-1.5 全完了が前提
                    → Sprint 1.7 (E2E Test)
```

**ボトルネック**: Sprint 1.2 (LLM Layer) と Sprint 1.3 (Task Graph Engine) が最もクリティカル。ここに最も多くの時間を確保する。

---

## Phase 別 成功指標

| Phase | 指標 | 目標値 |
|---|---|---|
| 1 | $0 パスでタスク完了 | Yes |
| 1 | Ollama 推論レイテンシ | < 10 秒 |
| 2 | 並列実行速度向上率 | 3x+ |
| 2 | Interactive Planning 承認率 | > 80% |
| 3 | メモリ圧縮率 | 98% (10K→500 tokens) |
| 3 | コンテキスト復元精度 | > 90% |
| 4 | Agent CLI ルーティング正確性 | > 85% |
| 5 | ツール自動発見成功率 | > 60% |
| 6 | 月次改善率 | +15% |
| 7 | SWE-bench lite スコア | TBD |
