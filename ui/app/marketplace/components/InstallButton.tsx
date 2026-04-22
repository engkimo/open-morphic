"use client";

import { useState } from "react";

interface InstallButtonProps {
  toolName: string;
  installed?: boolean;
  onInstall: (name: string) => Promise<void>;
  onUninstall?: (name: string) => Promise<void>;
}

export default function InstallButton({
  toolName,
  installed,
  onInstall,
  onUninstall,
}: InstallButtonProps) {
  const [loading, setLoading] = useState(false);
  const [confirm, setConfirm] = useState(false);

  async function handleInstall() {
    setLoading(true);
    try {
      await onInstall(toolName);
    } finally {
      setLoading(false);
    }
  }

  async function handleUninstall() {
    if (!confirm) {
      setConfirm(true);
      return;
    }
    setLoading(true);
    try {
      await onUninstall?.(toolName);
    } finally {
      setLoading(false);
      setConfirm(false);
    }
  }

  if (installed && onUninstall) {
    return (
      <button
        onClick={handleUninstall}
        disabled={loading}
        className={`rounded px-3 py-1.5 font-mono text-xs font-semibold transition-opacity hover:opacity-90 disabled:opacity-40 ${
          confirm
            ? "bg-danger/20 text-danger"
            : "bg-border text-text-muted"
        }`}
      >
        {loading ? "..." : confirm ? "Confirm?" : "Uninstall"}
      </button>
    );
  }

  return (
    <button
      onClick={handleInstall}
      disabled={loading || installed}
      className="rounded bg-accent/20 px-3 py-1.5 font-mono text-xs font-semibold text-accent transition-opacity hover:opacity-90 disabled:opacity-40"
    >
      {loading ? "Installing..." : installed ? "Installed" : "Install"}
    </button>
  );
}
