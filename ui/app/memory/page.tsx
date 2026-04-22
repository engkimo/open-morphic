"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import {
  searchMemory,
  exportContext,
  type MemorySearchResponse,
  type ContextExportResponse,
} from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";

const PLATFORMS = [
  { value: "claude_code", label: "Claude Code" },
  { value: "chatgpt", label: "ChatGPT" },
  { value: "cursor", label: "Cursor" },
  { value: "gemini", label: "Gemini" },
];

function SearchSection() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MemorySearchResponse | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    try {
      const data = await searchMemory(query.trim());
      setResults(data);
    } catch {
      /* backend may be down */
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-text-muted">Semantic Memory Search</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={handleSearch} className="flex gap-3">
          <Input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search memories... (e.g. 'authentication design decisions')"
            disabled={loading}
            className="flex-1"
          />
          <Button type="submit" disabled={loading || !query.trim()}>
            {loading ? "Searching..." : "Search"}
          </Button>
        </form>

        {results && (
          <div className="space-y-2">
            <div className="flex items-center gap-3 text-sm">
              <span className="text-text-muted">Query:</span>
              <span className="font-mono text-accent">{results.query}</span>
              <span className="text-text-muted">
                {results.count} result{results.count !== 1 ? "s" : ""}
              </span>
            </div>
            {results.count === 0 ? (
              <p className="py-4 text-center text-sm text-text-muted">
                No matching memories found.
              </p>
            ) : (
              <ScrollArea className="max-h-80">
                <div className="space-y-2">
                  {results.results.map((item, i) => (
                    <div
                      key={i}
                      className="rounded border border-border bg-background p-3"
                    >
                      <pre className="whitespace-pre-wrap font-mono text-xs text-foreground">
                        {item}
                      </pre>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ExportSection() {
  const [platform, setPlatform] = useState("claude_code");
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<ContextExportResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  async function handleExport(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setCopied(false);
    try {
      const data = await exportContext(platform, query.trim());
      setResult(data);
    } catch {
      /* backend may be down */
    } finally {
      setLoading(false);
    }
  }

  const handleCopy = useCallback(async () => {
    if (!result) return;
    await navigator.clipboard.writeText(result.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [result]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-text-muted">Context Export (Cross-Platform Bridge)</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={handleExport} className="flex gap-3">
          <select
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
            className="rounded-md border border-input bg-transparent px-3 py-1 font-mono text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          >
            {PLATFORMS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
          <Input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Optional: filter by topic..."
            disabled={loading}
            className="flex-1"
          />
          <Button type="submit" disabled={loading}>
            {loading ? "Exporting..." : "Export"}
          </Button>
        </form>

        {result && (
          <div className="space-y-3">
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-4">
                <span className="text-text-muted">Platform:</span>
                <span className="font-mono text-accent">{result.platform}</span>
                <span className="text-text-muted">
                  ~{result.token_estimate.toLocaleString()} tokens
                </span>
              </div>
              <Button variant="secondary" size="xs" onClick={handleCopy}>
                {copied ? "Copied!" : "Copy"}
              </Button>
            </div>
            <ScrollArea className="max-h-80 rounded border border-border bg-background p-3">
              <pre className="whitespace-pre-wrap font-mono text-xs text-foreground">
                {result.content}
              </pre>
            </ScrollArea>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function MemoryPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="link" size="sm" asChild>
          <Link href="/">&larr; Dashboard</Link>
        </Button>
        <h1 className="font-mono text-lg font-semibold tracking-tight">
          Semantic Memory
        </h1>
      </div>

      {/* Info banner */}
      <Card className="border-accent/30 bg-accent/5">
        <CardContent className="p-3 text-sm">
          <p className="text-text-muted">
            <span className="font-semibold text-accent">L1-L4 Memory Hierarchy</span>
            {" "}&mdash; Search across all memory layers (Active Context, Semantic Cache,
            Structured Facts, Cold Storage). Export context for use in other AI platforms.
          </p>
        </CardContent>
      </Card>

      <SearchSection />
      <ExportSection />
    </div>
  );
}
