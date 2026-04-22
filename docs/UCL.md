# Unified Cognitive Layer (UCL) — v0.5

> 全エージェントの記憶・タスク状態・判断を統合する共有認知層。A2Aを超え、共有認知へ。
> 個々のAIは「脳の領域」、UCLは「記憶と意識の統合」。

## コンセプト

```
A2A (Agent-to-Agent): メッセージのやり取り
UCL (Unified Cognitive): 共有された「意識」と「記憶」

タスクを Agent A → Agent B に渡すとき、
- 判断の経緯 (Decision)
- 中間成果物 (Artifact)
- 残ったブロッカー (Blocker)
- エージェント行動履歴 (AgentAction)
を完全に引き継ぐ。
```

## ドメインモデル

```python
@dataclass
class SharedTaskState:
    """全エージェント共有のタスク状態"""
    task_id: str
    goal: str
    current_agent: str
    decisions: list[Decision]            # 判断履歴
    artifacts: list[Artifact]            # 成果物
    blockers: list[Blocker]              # 未解決ブロッカー
    agent_actions: list[AgentAction]     # 全エージェント行動履歴
    handoff_history: list[Handoff]       # 引き継ぎログ

@dataclass
class Decision:
    timestamp: datetime
    agent: str
    reasoning: str
    choice: str
    alternatives_rejected: list[str]
    confidence: float  # 0-1

@dataclass
class CognitiveMemory:
    """UCL 共有メモリエントリ"""
    content: str
    source_agent: str
    type: Literal["fact", "judgment", "pattern", "failure"]
    confidence: float
    created_at: datetime
    referenced_by: list[str]  # 参照したエージェント
```

## Context Adapters

OSのデバイスドライバ的設計。各エンジン用の双方向コンテキスト変換。

```python
class ContextAdapter(Protocol):
    """各エンジンごとのコンテキスト変換"""
    def inject(self, ucl_state: SharedTaskState) -> EngineContext:
        """UCL → エンジン固有形式"""
        ...
    def extract(self, engine_output: Any) -> UCLUpdate:
        """エンジン出力 → UCL 更新"""
        ...

# 実装例
class ClaudeCodeAdapter(ContextAdapter):
    def inject(self, state):
        return CLAUDE_MD_FORMAT + state.to_markdown()
    def extract(self, session_log):
        return self.parse_claude_session(session_log)

class GeminiCLIAdapter(ContextAdapter):
    def inject(self, state):
        return GEMINI_AGENTS_FORMAT + state.to_yaml()
    def extract(self, log):
        return self.parse_gemini_events(log)

class CodexAdapter(ContextAdapter):
    def inject(self, state):
        return AGENTS_MD_FORMAT + state.to_agents_md()
    ...
```

## Insight Extraction Pipeline

```python
class InsightExtractor:
    """実行後の自動知識抽出 → UCL メモリ + タスク状態更新"""

    async def extract(self, session: AgentSession) -> list[CognitiveMemory]:
        # LLMで "驚き度 (surprise)" が高い出来事だけ抽出
        insights = await self.llm.extract_insights(
            session.transcript,
            prompt="Extract facts, patterns, failures worth remembering"
        )
        for insight in insights:
            insight.embedding = self.embed(insight.content)
            insight.source_agent = session.agent_name
            await self.ucl.add_memory(insight)
        return insights
```

## Agent Affinity Scoring

```python
class AgentAffinity:
    """どのエンジンがこのトピックを最も理解しているか"""

    def score(self, topic: str, agent: str) -> float:
        """
        UCLメモリ中で、そのエージェントが source_agent の
        エントリが topic にどれだけマッチするか
        """
        memories = self.ucl.search_by_source(agent)
        return self.similarity(topic, memories)

    async def best_agent_for(self, task: Task) -> str:
        scores = {a: self.score(task.topic, a) for a in ALL_AGENTS}
        return max(scores, key=scores.get)
```

## Task Handoff

```python
class TaskHandoff:
    """Agent A → Agent B、完全引き継ぎ"""

    async def handoff(
        self,
        task: Task,
        from_agent: str,
        to_agent: str,
        reason: str
    ) -> HandoffResult:
        # 1. from_agent の最終状態をスナップショット
        state = await self.ucl.get_task_state(task.id)

        # 2. to_agent 用にアダプタ変換
        adapter = self.adapters[to_agent]
        context = adapter.inject(state)

        # 3. ハンドオフログ記録
        handoff = Handoff(
            from_agent=from_agent,
            to_agent=to_agent,
            reason=reason,
            state_snapshot_id=state.id,
            timestamp=datetime.now(),
        )
        state.handoff_history.append(handoff)

        # 4. to_agent 起動
        return await self.engines[to_agent].resume(context)
```

## Conflict Resolver

```python
class ConflictResolver:
    """エージェント間の矛盾検出・信頼度重み付き解決"""

    async def detect_conflicts(self, task_id: str) -> list[Conflict]:
        memories = self.ucl.get_memories_for_task(task_id)
        contradictions = await self.llm.find_contradictions(memories)
        return contradictions

    async def resolve(self, conflict: Conflict) -> Resolution:
        # 信頼度 × recency × affinity で重み付け
        weights = {
            m.source_agent: m.confidence * self.decay(m.created_at)
                           * self.affinity.score(conflict.topic, m.source_agent)
            for m in conflict.memories
        }
        winner = max(weights, key=weights.get)
        return Resolution(chosen=winner, reasoning=weights)
```

## Phase 7 実装ステップ (16週)

1. **UCL ドメインモデル**: `SharedTaskState`, `Decision`, `AgentAction`, `CognitiveMemory`
2. **Context Adapters**: 6 エンジン分の inject/extract (Claude Code / Gemini / Codex / Ollama / OpenHands / ADK)
3. **Insight Extraction Pipeline**: 実行後自動抽出 → UCL 更新
4. **Agent Affinity Scoring**: トピック × エージェント スコアリング
5. **Task Handoff**: 判断・成果物・ブロッカー含む完全引き継ぎ
6. **Conflict Resolver**: 矛盾検出 + 信頼度重み付き解決
7. **UCL API + CLI + UI**: 外部アクセス層
8. **Integration Tests**: クロスエンジンコンテキスト継続性ベンチマーク

## 差別化

他フレームワークにない独自性。LangGraph は単一プロセス内の共有状態を持つが、**マルチエンジン (異なる AI プロバイダー) 間の共有認知**を正面から設計するのは UCL が初めて。
