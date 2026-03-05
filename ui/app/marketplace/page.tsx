"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  searchTools,
  installTool,
  uninstallTool,
  listInstalledTools,
  type ToolCandidateResponse,
} from "@/lib/api";
import SearchBar from "./components/SearchBar";
import ToolCard from "./components/ToolCard";

export default function MarketplacePage() {
  const [results, setResults] = useState<ToolCandidateResponse[]>([]);
  const [installed, setInstalled] = useState<ToolCandidateResponse[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<"search" | "installed">("search");

  const installedNames = new Set(installed.map((t) => t.name));

  const refreshInstalled = useCallback(async () => {
    try {
      const list = await listInstalledTools();
      setInstalled(list);
    } catch {
      /* backend may be down */
    }
  }, []);

  useEffect(() => {
    refreshInstalled();
  }, [refreshInstalled]);

  async function handleSearch(query: string) {
    setLoading(true);
    setSearchError(null);
    try {
      const data = await searchTools(query);
      setResults(data.candidates);
      setTotalCount(data.total_count);
      if (data.error) setSearchError(data.error);
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleInstall(name: string) {
    await installTool(name);
    await refreshInstalled();
  }

  async function handleUninstall(name: string) {
    await uninstallTool(name);
    await refreshInstalled();
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link
            href="/"
            className="text-sm text-text-muted hover:text-accent"
          >
            &larr; Dashboard
          </Link>
          <h2 className="font-mono text-lg font-bold tracking-tight">
            Marketplace
          </h2>
        </div>
        <Link
          href="/models"
          className="text-sm text-text-muted hover:text-accent"
        >
          Model Management &rarr;
        </Link>
      </div>

      <div className="flex rounded-lg border border-border">
        <button
          onClick={() => setTab("search")}
          className={`px-3 py-1.5 text-sm font-medium ${
            tab === "search"
              ? "bg-accent text-white"
              : "text-text-muted hover:text-foreground"
          } rounded-l-lg`}
        >
          Search
        </button>
        <button
          onClick={() => setTab("installed")}
          className={`px-3 py-1.5 text-sm font-medium ${
            tab === "installed"
              ? "bg-accent text-white"
              : "text-text-muted hover:text-foreground"
          } rounded-r-lg`}
        >
          Installed ({installed.length})
        </button>
      </div>

      {tab === "search" && (
        <div className="space-y-4">
          <SearchBar onSearch={handleSearch} disabled={loading} />

          {searchError && (
            <p className="text-sm text-danger">{searchError}</p>
          )}

          {loading && (
            <p className="py-4 text-center text-sm text-text-muted">
              Searching...
            </p>
          )}

          {!loading && results.length > 0 && (
            <>
              <p className="text-xs text-text-muted">
                {totalCount} result{totalCount !== 1 && "s"} found
              </p>
              <div className="space-y-2">
                {results.map((tool) => (
                  <ToolCard
                    key={tool.name}
                    tool={tool}
                    installed={installedNames.has(tool.name)}
                    onInstall={handleInstall}
                    onUninstall={handleUninstall}
                  />
                ))}
              </div>
            </>
          )}

          {!loading && results.length === 0 && !searchError && (
            <p className="py-8 text-center text-sm text-text-muted">
              Search for MCP tools to get started.
            </p>
          )}
        </div>
      )}

      {tab === "installed" && (
        <div className="space-y-2">
          {installed.length === 0 ? (
            <p className="py-8 text-center text-sm text-text-muted">
              No tools installed yet. Search and install tools above.
            </p>
          ) : (
            installed.map((tool) => (
              <ToolCard
                key={tool.name}
                tool={tool}
                installed
                onInstall={handleInstall}
                onUninstall={handleUninstall}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}
