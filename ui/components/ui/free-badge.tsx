import * as React from "react";
import { Badge } from "./badge";
import { cn } from "@/lib/utils";

interface FreeBadgeProps {
  className?: string;
}

export function FreeBadge({ className }: FreeBadgeProps) {
  return (
    <Badge variant="free" className={cn("text-[9px]", className)}>
      FREE
    </Badge>
  );
}
