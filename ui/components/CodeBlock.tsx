"use client";

import { useCallback, useState } from "react";
import { Copy, Check, Code2 } from "lucide-react";

interface CodeBlockProps {
  code: string;
  language?: string;
}

export default function CodeBlock({ code, language }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [code]);

  return (
    <div className="relative rounded-lg border border-border bg-[#0D0D14] overflow-hidden">
      {/* Header: language label + copy button */}
      <div className="flex items-center justify-between border-b border-border bg-[#12121A] px-3 py-1.5">
        <span className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider text-text-muted">
          <Code2 size={11} />
          {language || "code"}
        </span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-[10px] font-mono text-text-muted hover:text-accent transition-colors"
        >
          {copied ? (
            <>
              <Check size={11} className="text-success" /> Copied
            </>
          ) : (
            <>
              <Copy size={11} /> Copy
            </>
          )}
        </button>
      </div>
      {/* Code content */}
      <pre className="overflow-x-auto p-3 text-xs leading-relaxed">
        <code className="font-mono text-emerald-300">{code}</code>
      </pre>
    </div>
  );
}
