"use client";

import { CheckCircle2, XCircle, Cpu } from "lucide-react";
import type { ModelStatus as ModelStatusType } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface ModelStatusProps {
  status: ModelStatusType | null;
}

export default function ModelStatus({ status }: ModelStatusProps) {
  if (!status) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5 text-text-muted">
          <Cpu size={14} />
          Models
        </CardTitle>
      </CardHeader>
      <CardContent className="text-sm">
        <div className="flex items-center gap-2 mb-3">
          {status.ollama_running ? (
            <CheckCircle2 size={14} className="text-success" />
          ) : (
            <XCircle size={14} className="text-danger" />
          )}
          <span className="text-text-muted">
            Ollama {status.ollama_running ? "Online" : "Offline"}
          </span>
        </div>
        {status.models.length > 0 && (
          <div className="space-y-1">
            {status.models.map((m) => (
              <div
                key={m.name}
                className="flex items-center justify-between text-xs"
              >
                <span className="font-mono">{m.name}</span>
                {m.name === status.default_model && (
                  <Badge variant="engine">default</Badge>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
