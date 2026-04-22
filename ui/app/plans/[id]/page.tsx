"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import PlanningView from "@/components/PlanningView";
import { getPlan, type ExecutionPlanResponse } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function PlanPage() {
  const params = useParams<{ id: string }>();
  const [plan, setPlan] = useState<ExecutionPlanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!params.id) return;

    getPlan(params.id)
      .then(setPlan)
      .catch(() => setError("Plan not found"));
  }, [params.id]);

  return (
    <div className="space-y-4">
      <Button variant="link" size="sm" asChild>
        <Link href="/">&larr; Back to Dashboard</Link>
      </Button>

      {error && <p className={cn("text-sm text-destructive")}>{error}</p>}
      {plan && <PlanningView plan={plan} />}
    </div>
  );
}
