import * as React from "react";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "./card";

interface StatsCardProps {
  label: string;
  value: string;
  color?: string;
  sub?: string;
  className?: string;
}

export function StatsCard({ label, value, color, sub, className }: StatsCardProps) {
  return (
    <Card className={className}>
      <CardContent className="p-3 text-center">
        <div className={cn("text-lg font-bold font-mono", color)}>
          {value}
        </div>
        <div className="text-[10px] text-text-muted">{label}</div>
        {sub && <div className="text-[9px] text-text-muted">{sub}</div>}
      </CardContent>
    </Card>
  );
}
