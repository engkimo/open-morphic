"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import PlanningView from "@/components/PlanningView";
import { getPlan, type ExecutionPlanResponse } from "@/lib/api";

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
      <Link
        href="/"
        className="inline-block text-sm text-text-muted hover:text-accent"
      >
        &larr; Back to Dashboard
      </Link>

      {error && <p className="text-danger">{error}</p>}
      {plan && <PlanningView plan={plan} />}
    </div>
  );
}
