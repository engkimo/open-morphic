"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ListTodo,
  ClipboardList,
  Server,
  DollarSign,
  Store,
  Cpu,
  Brain,
  Network,
  TrendingUp,
  BarChart3,
  Settings,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const NAV_ITEMS = [
  { href: "/tasks", label: "Tasks", icon: ListTodo },
  { href: "/plans", label: "Plans", icon: ClipboardList },
  { href: "/engines", label: "Engines", icon: Server },
  { href: "/cost", label: "Cost", icon: DollarSign },
  { href: "/marketplace", label: "Marketplace", icon: Store },
  { href: "/models", label: "Models", icon: Cpu },
  { href: "/memory", label: "Memory", icon: Brain },
  { href: "/a2a", label: "A2A", icon: Network },
  { href: "/evolution", label: "Evolution", icon: TrendingUp },
  { href: "/cognitive", label: "Cognitive", icon: Brain },
  { href: "/benchmarks", label: "Benchmarks", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: Settings },
];

export default function NavBar() {
  const pathname = usePathname();

  return (
    <nav className="flex items-center gap-1 text-sm">
      {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
        const active = pathname === href || pathname?.startsWith(href + "/");
        return (
          <Button
            key={href}
            variant="ghost"
            size="xs"
            asChild
            className={cn(
              active && "bg-primary/10 text-primary",
            )}
          >
            <Link href={href}>
              <Icon size={14} />
              <span className="hidden lg:inline">{label}</span>
            </Link>
          </Button>
        );
      })}
    </nav>
  );
}
