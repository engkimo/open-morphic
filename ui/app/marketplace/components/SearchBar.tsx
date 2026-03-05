"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface SearchBarProps {
  onSearch: (query: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export default function SearchBar({
  onSearch,
  disabled,
  placeholder = "Search MCP tools...",
}: SearchBarProps) {
  const [query, setQuery] = useState("");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const debouncedSearch = useCallback(
    (value: string) => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        const trimmed = value.trim();
        if (trimmed.length >= 2) onSearch(trimmed);
      }, 400);
    },
    [onSearch],
  );

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const value = e.target.value;
    setQuery(value);
    debouncedSearch(value);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (timerRef.current) clearTimeout(timerRef.current);
    const trimmed = query.trim();
    if (trimmed) onSearch(trimmed);
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-3">
      <input
        type="text"
        value={query}
        onChange={handleChange}
        placeholder={placeholder}
        disabled={disabled}
        className="flex-1 rounded-lg border border-border bg-surface px-4 py-3 font-mono text-sm text-foreground placeholder:text-text-muted focus:border-accent focus:outline-none"
      />
      <button
        type="submit"
        disabled={disabled || !query.trim()}
        className="rounded-lg bg-accent px-6 py-3 font-mono text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-40"
      >
        Search
      </button>
    </form>
  );
}
