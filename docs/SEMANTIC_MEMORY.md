# Semantic Memory & Context Compression (v0.3)

> 「全部覚えようとするな、クエリに答えるのに必要な記憶だけを動的に召喚せよ」
> — CPUキャッシュ階層と同じ設計思想

## なぜ単純な要約では駄目か

```
素朴な要約アプローチの失敗:
会話1000回分 → LLMで要約 → 500トークン

問題①: 要約時点では「何が重要か」がわからない
問題②: 要約のたびに情報が劣化 (不可逆圧縮)
問題③: 「あの時のニュアンス」が消える
問題④: 要約コスト自体が積み上がる

Hash的アプローチの本質:
情報を「捨てる」のではなく「アクセスを遅延させる」
→ クエリが来た時に必要な記憶だけを動的に召喚
```

## Memory Hierarchy — L1〜L4

```
┌────────────────────────────────────────────────────────────────┐
│                  Morphic-Agent Memory Hierarchy                │
│                                                                │
│  L1: Active Context (今のトークンウィンドウ)                   │
│  ├── 直近N発言 raw保持                                         │
│  └── ~2,000 tokens                          [最高速・最小]     │
│                                                                │
│  L2: Semantic Cache (意味的Hash層) ←── 核心                   │
│  ├── 発言を Embedding でベクトル化                             │
│  ├── LSH (Locality Sensitive Hashing) でバケット化             │
│  ├── 類似発言は clustering して代表ベクトルに圧縮              │
│  └── 「何を言ったか」→「どの意味空間にいるか」に変換            │
│                                                                │
│  L3: Structured Facts (知識グラフ層)                           │
│  ├── エンティティ・関係の抽出・正規化                          │
│  └── "Shimizu, project, deadline=3月" のようなトリプル         │
│                                                                │
│  L4: Cold Storage (完全ログ)                                   │
│  └── 生テキスト全保存、L1-3 で miss したときのみ召喚           │
│                                             [最低速・最大]    │
└────────────────────────────────────────────────────────────────┘
```

## Semantic Fingerprint — LSH

```python
import numpy as np
from sentence_transformers import SentenceTransformer

class SemanticMemory:
    """
    通常の Hash: 異なる入力 → 異なる Hash
    LSH: 意味が近い入力 → 同じ Hash

    → 「清水建設の話」は何百回しても同じ cluster にまとめられ圧縮
    → クエリ時に O(1) に近い速度で関連記憶を取得
    """
    def __init__(self):
        self.model = SentenceTransformer("text-embedding-3-small")
        self.store: dict[str, dict] = {}
        self.cluster_map: dict[str, list] = {}

    def add(self, text: str) -> str:
        embedding = self.model.encode(text)
        semantic_hash = self._lsh(embedding)
        existing = self._find_similar(embedding, threshold=0.92)
        if existing:
            self._reinforce(existing["hash"], text)
            return existing["hash"]
        self.store[semantic_hash] = {
            "text": text,
            "embedding": embedding,
            "access_count": 1,
            "compressed_summary": None,
            "created_at": datetime.now(),
            "last_accessed": datetime.now(),
        }
        return semantic_hash

    def _lsh(self, embedding: np.ndarray, n_planes: int = 32) -> str:
        random_planes = np.random.randn(n_planes, len(embedding))
        binary_code = (embedding @ random_planes.T > 0).astype(int)
        return format(int("".join(map(str, binary_code)), 2), "08x")
```

## 圧縮3戦略

### 戦略①: Hierarchical Summarization(木構造圧縮)
```
Level 0 (葉): "QuickSuite の User per Author ライセンスは月 $18/user"
Level 1:      "QuickSuite ライセンス構造の詳細"
Level 2:      "清水建設向けコスト試算の前提条件"
Level 3 (根): "清水建設 QuickSuite プロジェクトの概要"

→ 概要質問 → Level3のみ参照 (~10tokens)
→ 詳細質問 → Level0まで掘り下げ (~500tokens)
```

### 戦略②: Forgetting Curve(エビングハウス忘却曲線)
```python
class ForgettingMemory:
    def retention_score(self, memory: dict) -> float:
        """R = e^(-t/S)"""
        hours_elapsed = (datetime.now() - memory["last_accessed"]).seconds / 3600
        stability = (1.0
                    + memory["access_count"] * 0.5
                    + memory["importance_score"] * 2.0)
        return math.exp(-hours_elapsed / (stability * 24))

    def compress_expired(self):
        """保持スコア < 0.3 の記憶を要約してL3に昇格後、削除"""
        for hash_id, memory in list(self.store.items()):
            if self.retention_score(memory) < 0.3:
                self._promote_to_facts(memory)
                del self.store[hash_id]
```

### 戦略③: Delta Encoding(Git方式差分保存)
```
Base State: "清水建設プロジェクト = {ライセンス: 未決, 予算: 未定}"
Delta 1:    "+ライセンス決定: User per Author, 50人"
Delta 2:    "+予算承認: $54,000/年"
Delta 3:    "+懸念事項: Lake Formation との IAM 権限"

Current State = Base + Delta1 + Delta2 + Delta3

→ 「現在の状態」だけなら Base + 最新 Delta のみ参照で済む
→ 「経緯が知りたい」ときのみ全 Delta を展開
```

## ContextZipper — クエリ適応型圧縮

```python
class ContextZipper:
    """
    AI に渡すコンテキストをリアルタイム圧縮するミドルウェア
    目標: 10,000 トークンの会話履歴 → 500 トークンに圧縮しつつ情報保持

    重要: 同じ会話履歴でも、クエリによって異なる最適コンテキストが生成される
    """
    def compress(self, conversation_history: list, current_query: str) -> str:
        relevant_memories = self.semantic_memory.retrieve(query=current_query, top_k=10)
        entities = self.extract_entities(current_query)
        relevant_facts = self.fact_store.query(entities)

        budget = self.target_tokens
        compressed = [f"[Facts] {relevant_facts}"]
        budget -= self.count_tokens(str(relevant_facts))
        for memory in relevant_memories:
            if budget <= 0:
                break
            tokens = self.count_tokens(memory["text"])
            if tokens <= budget:
                compressed.append(memory["text"])
                budget -= tokens
            else:
                compressed.append(memory["compressed_summary"] or "")
                budget -= 30
        return "\n---\n".join(compressed)
```

## 最先端研究との接続

| 研究 | 内容 | Morphic-Agentへの応用 |
|---|---|---|
| **MemGPT / Letta** | OS のページング思想を LLM に適用。L1/L2/L3 階層を先行実装 | `pip install letta` で即使用可能 |
| **Mamba / SSM** | 無限の文脈を固定サイズの「状態ベクトル」に圧縮し続ける | Semantic Hash の理論的根拠 |
| **Titans (Google 2024)** | "驚き度(surprise)が高い情報だけをメモリに書き込む" 選択的記憶 | ForgettingCurve の importance_score に応用 |
| **mem0** | LLM で会話から自動抽出・ベクトル DB 保存 | L2 の実装として即使用可能 |

**推奨スタート構成:**
```python
# Phase 1: mem0 だけで 8 割の問題を解決
from mem0 import Memory
memory = Memory()

# Phase 2: pgvector + ContextZipper で精度向上
# Phase 3: Knowledge Graph + Delta Encoding で完全実装
```
