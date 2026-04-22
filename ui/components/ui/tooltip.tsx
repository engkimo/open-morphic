"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

// Lightweight tooltip without radix dependency
// Shows on hover with a simple absolute-positioned element

interface TooltipProviderProps {
  children: React.ReactNode;
}

function TooltipProvider({ children }: TooltipProviderProps) {
  return <>{children}</>;
}

interface TooltipProps {
  children: React.ReactNode;
}

function Tooltip({ children }: TooltipProps) {
  return <div className="relative inline-flex">{children}</div>;
}

function TooltipTrigger({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div {...props}>{children}</div>;
}

function TooltipContent({
  children,
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block z-50 rounded-md bg-foreground px-2 py-1 text-xs text-background shadow-md",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider };
