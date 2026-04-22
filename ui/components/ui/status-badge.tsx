import * as React from "react";
import { Badge, type BadgeProps } from "./badge";

const STATUS_VARIANT_MAP: Record<string, BadgeProps["variant"]> = {
  pending: "secondary",
  running: "info",
  success: "success",
  failed: "destructive",
  fallback: "warning",
  degraded: "warning",
  proposed: "info",
  approved: "success",
  rejected: "destructive",
  executed: "engine",
  active: "info",
  resolved: "success",
  expired: "warning",
};

interface StatusBadgeProps extends Omit<BadgeProps, "variant"> {
  status: string;
}

export function StatusBadge({ status, className, ...props }: StatusBadgeProps) {
  const variant = STATUS_VARIANT_MAP[status] || "secondary";
  return (
    <Badge variant={variant} className={className} {...props}>
      {status}
    </Badge>
  );
}
