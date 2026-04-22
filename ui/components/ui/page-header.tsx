import * as React from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { Button } from "./button";

interface PageHeaderProps {
  title: string;
  backHref?: string;
  backLabel?: string;
  children?: React.ReactNode;
  className?: string;
}

export function PageHeader({
  title,
  backHref = "/",
  backLabel = "Dashboard",
  children,
  className,
}: PageHeaderProps) {
  return (
    <div className={cn("flex items-center justify-between", className)}>
      <div className="flex items-center gap-4">
        <Button variant="link" size="sm" asChild className="text-text-muted px-0">
          <Link href={backHref}>&larr; {backLabel}</Link>
        </Button>
        <h1 className="font-mono text-lg font-semibold tracking-tight">
          {title}
        </h1>
      </div>
      {children && <div className="flex items-center gap-2">{children}</div>}
    </div>
  );
}
