# UI Design — "Mission Control for Intelligence"

## Theme

```typescript
export const morphicTheme = {
  colors: {
    background:   '#0A0A0F',  // 深宇宙ブラック
    surface:      '#12121A',  // ダークネイビー
    border:       '#1E1E2E',  // 微細ボーダー
    accent:       '#6366F1',  // インディゴ (主要アクション)
    success:      '#10B981',  // エメラルド (完了)
    warning:      '#F59E0B',  // アンバー (コスト警告)
    danger:       '#EF4444',  // レッド (失敗)
    info:         '#38BDF8',  // スカイブルー (実行中)
    localFree:    '#34D399',  // ブライトグリーン (LOCAL FREE表示)
    text:         '#E2E8F0',
    textMuted:    '#94A3B8',
  },
  fonts: {
    heading: "'Geist', 'Inter', sans-serif",
    mono:    "'JetBrains Mono', 'Fira Code', monospace",
  },
}

const TaskNodeStyles = {
  pending:  { border: '#2D2D42', icon: '⏳' },
  running:  { border: '#38BDF8', icon: '⚡', pulse: true },
  success:  { border: '#10B981', icon: '✓' },
  failed:   { border: '#EF4444', icon: '✗' },
  fallback: { border: '#F59E0B', icon: '↻' },
  local:    { badge: 'FREE', badgeColor: '#34D399' },
}
```

## Layout

```
┌─────────────────────────────────────────────────────────┐
│ [Morphic-Agent]  [New Task]  [Marketplace]  [Settings]  │ ← ヘッダー
├──────────┬──────────────────────────────┬──────────────┤
│ Tasks    │   TASK GRAPH VISUALIZER      │ Context      │
│ ├ Active │                              │ Bridge       │
│ │ ○ A    │   [Goal]──[A]──[A1]──[✓]    │ ─────────    │
│ │ ─ B    │         └─[B]──[B1]──[↻]    │ Cost: $0.00  │
│ ├History │                              │ LOCAL: 87%   │
│ └ Tools  │   [Execute] [Plan] [Pause]   │ Cache: 92%   │
├──────────┴──────────────────────────────┴──────────────┤
│ ⚡ Running: sub_task_B  |  🔋 qwen3:8b (LOCAL FREE)    │ ← ステータスバー
└─────────────────────────────────────────────────────────┘
```
