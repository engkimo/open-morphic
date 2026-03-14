"use client";

import CodeBlock from "./CodeBlock";

interface ExecutionResultProps {
  code: string;
  language?: string;
  output: string | null;
  success?: boolean;
}

export default function ExecutionResult({
  code,
  language,
  output,
  success = true,
}: ExecutionResultProps) {
  return (
    <div className="space-y-2">
      {/* Code section */}
      <CodeBlock code={code} language={language} />

      {/* Execution output */}
      {output && (
        <div className="rounded-lg border border-border overflow-hidden">
          <div className="flex items-center gap-2 border-b border-border bg-[#12121A] px-3 py-1.5">
            <span
              className={`h-2 w-2 rounded-full ${success ? "bg-success" : "bg-danger"}`}
            />
            <span className="text-[10px] font-mono uppercase tracking-wider text-text-muted">
              Output
            </span>
          </div>
          <pre className="overflow-x-auto bg-[#0A0A0F] p-3 text-xs leading-relaxed">
            <code className={`font-mono ${success ? "text-text" : "text-danger"}`}>
              {output}
            </code>
          </pre>
        </div>
      )}
    </div>
  );
}
