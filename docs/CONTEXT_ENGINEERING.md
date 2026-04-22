# Context Engineering — Manus 5原則

> Manusが4回作り直して到達した鉄則。Morphic-Agentはこれを**最初から**組み込む。

---

## 原則 1: KV-Cache を設計の中心に置く

**なぜ重要か:** Claude Sonnetでは、キャッシュ済みトークンは $0.30/MTok、未キャッシュは $3/MTok(**10倍差**)。エージェントのinput:output比は約100:1なので、キャッシュ設計だけでコストを劇的に削減できる。

```python
# ✅ 正しい設計: システムプロンプトの先頭を安定させる
SYSTEM_PROMPT_PREFIX = """
You are Morphic-Agent, a self-evolving AI agent...
[ここは絶対に変えない安定した記述]
"""
# 日時・セッション情報は末尾か動的セクションに置く

# ❌ NG パターン (毎回キャッシュ無効化)
# SYSTEM_PROMPT = f"Current time: {datetime.now().isoformat()}\n..."

# ✅ コンテキストはappend-only(過去を修正しない)
class AgentContext:
    def append_action(self, action): ...    # 追記のみ
    def append_observation(self, obs): ...  # 追記のみ
    # serialize() は常に決定論的 (JSON sort_keys=True)
```

**実装指針:**
- システムプロンプト先頭は不変(日時は末尾か動的セクション)
- JSON/XMLシリアライズは `sort_keys=True` で決定論的に
- キャッシュブレークポイントはシステムプロンプト末尾に手動設置
- セルフホスト(vLLM等)の場合はprefix cachingを有効化

---

## 原則 2: ツールは「マスク」する。削除しない

**なぜ重要か:** ツールを動的追加・削除するとKVキャッシュが無効化される。過去のアクションが未定義ツールを参照して混乱も生じる。

```python
class ToolStateMachine:
    """コンテキスト依存でツール使用可否を制御。定義は常に全量保持。"""
    def get_allowed_tools(self, state: AgentState) -> list[str]:
        all_tools = self.registry.get_all()  # 常に全ツール定義
        return [t for t in all_tools if self._is_allowed(t, state)]
```

**ツール命名規則(プレフィックスでグループ制御):**
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

## 原則 3: ファイルシステムを「無限のコンテキスト」として使う

```python
class FileSystemContext:
    """圧縮は「復元可能な形式」のみ許可。情報損失ゼロ。"""
    def compress_webpage(self, url: str, content: str) -> str:
        self.save(f"cache/{hash(url)}.txt", content)
        return f"[Cached at cache/{hash(url)}.txt, URL: {url}]"
    # URLが残れば再取得可能 → コンテキストからは省略OK
```

---

## 原則 4: `todo.md` でアテンションを操作する

LLMは文脈の先頭・末尾に最も注目する(中間希薄化)。現在のゴールと進捗を繰り返し「再引用」することで長タスクのドリフトを防ぐ。

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

## 原則 5: 観察の多様性を意図的に維持する

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

## Industry Best Practices — 業界鉄則

### Cursor (Agent Prompt 2025-09-03)
1. "Keep going until query is COMPLETELY resolved" → 解決するまで止まらない
2. "DEFAULT TO PARALLEL: always parallel unless output of A required for B" → 並列がデフォルト
3. "If you say you're about to do something, do it in the same turn" → 宣言したら即実行
4. "Check off TODOs before reporting progress" → 進捗報告前にtodo.mdを更新
5. "NEVER refer to tool names when speaking to USER" → ツール名でなく自然言語で説明

### Windsurf Cascade
1. Code/Chatの2モードで「変更あり/なし」を明確に分離
2. バックグラウンド計画エージェントで全体最適を維持
3. `.windsurfrules`的なルールファイルでプロジェクト固有制約を管理
4. 自動生成Memoriesでコーディングスタイル・APIを永続学習
5. "Before changes, present plan and ask for confirmation"

### Devin 2.0
1. Interactive Planning: 実行前に計画+コード引用で提示
2. Self-assessed confidence: タスク後に自己評価スコアを報告
3. Planning Checkpoint: 高リスク変更前は人間確認必須
4. 各タスクを独立VMで実行(隔離・並列)
5. Wiki/Search: コードベース構造を自動学習

### Manus Context Engineering Blog
1. KV-cacheヒット率が最重要メトリクス(10倍コスト差)
2. ツールは削除せずマスクで制御
3. ファイルシステムを無限の外部メモリとして使う
4. `todo.md`でアテンションを意図的に操作
5. 観察に多様性を入れてドリフトを防ぐ
6. "Stochastic Graduate Descent": 完璧より動作、学習しながら改善
