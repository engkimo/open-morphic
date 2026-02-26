# Morphic-Agent Chrome Extension — Specification

> **Status**: Deferred to Phase 5 (Marketplace & Tools)
> **Prerequisites**: MCP Server stable (Sprint 3.7), Context Bridge API (Sprint 3.6)

## Overview

Chrome Extension that automatically injects Morphic-Agent context when pasting into AI chat interfaces (Claude.ai, ChatGPT, Gemini, etc.).

## Architecture

```
[Chrome Extension]
    ├── manifest.json (Manifest v3)
    ├── service-worker.js        ← Background: MCP client or REST API
    ├── content-script.js        ← Injected into AI chat pages
    ├── popup/                   ← Extension popup UI
    │   ├── popup.html
    │   └── popup.js
    └── options/                 ← Settings page
        ├── options.html
        └── options.js

Communication:
  Extension  ──REST──▶  Morphic-Agent API (localhost:8000)
             └──MCP──▶  Morphic-Agent MCP Server (stdio or HTTP)
```

## API Contracts

### REST Endpoint (Sprint 3.6)

```
GET /api/memory/export?platform={platform}&q={query}&max_tokens={budget}

Response: {
  "platform": "chatgpt",
  "content": "...",
  "token_estimate": 450
}
```

### MCP Tool (Sprint 3.7)

```json
{
  "tool": "context_export",
  "arguments": {
    "platform": "claude_code",
    "query": "current project status",
    "max_tokens": 800
  }
}
```

## Content Script Targets

| Platform | URL Pattern | Injection Point |
|---|---|---|
| Claude.ai | `claude.ai/*` | Textarea `.ProseMirror` |
| ChatGPT | `chatgpt.com/*` | Textarea `#prompt-textarea` |
| Gemini | `gemini.google.com/*` | Rich text editor |
| Cursor | N/A (uses MCP directly) | — |

## Manifest v3 Sketch

```json
{
  "manifest_version": 3,
  "name": "Morphic-Agent Context Bridge",
  "version": "0.1.0",
  "permissions": ["activeTab", "storage", "clipboardRead"],
  "host_permissions": [
    "http://localhost:8000/*",
    "https://claude.ai/*",
    "https://chatgpt.com/*",
    "https://gemini.google.com/*"
  ],
  "background": {
    "service_worker": "service-worker.js"
  },
  "content_scripts": [{
    "matches": [
      "https://claude.ai/*",
      "https://chatgpt.com/*",
      "https://gemini.google.com/*"
    ],
    "js": ["content-script.js"]
  }],
  "action": {
    "default_popup": "popup/popup.html"
  },
  "options_page": "options/options.html"
}
```

## User Flow

1. User opens Claude.ai/ChatGPT/Gemini
2. Content script detects the AI chat interface
3. User triggers context injection (keyboard shortcut or popup button)
4. Extension calls `GET /api/memory/export?platform=chatgpt`
5. Response content is inserted into the chat input
6. User sends the message with full Morphic-Agent context

## Settings

- **API URL**: `http://localhost:8000` (default)
- **Auto-inject**: On/Off (inject on every paste)
- **Platform override**: Force a specific platform format
- **Token budget**: Max tokens for context export
- **Query**: Default search query for context relevance

## Build Toolchain

- **Bundler**: Vite + CRXJS plugin
- **Framework**: Preact (lightweight, <3kb)
- **TypeScript**: Strict mode
- **Testing**: Vitest + Playwright for E2E

## Implementation Timeline (Phase 5)

1. Manifest + service worker + popup UI
2. Content scripts for each platform
3. REST API integration
4. MCP client integration (optional, for direct server access)
5. Keyboard shortcut support
6. Auto-inject on paste detection
