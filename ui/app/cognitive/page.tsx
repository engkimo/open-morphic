"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  getCognitiveStates,
  getCognitiveState,
  getAffinityScores,
} from "@/lib/api";
import type {
  SharedTaskStateResponse,
  AffinityScoreResponse,
} from "@/lib/api";
import StateCard from "./components/StateCard";
import StateDetail from "./components/StateDetail";
import AffinityTable from "./components/AffinityTable";

export default function CognitivePage() {
  const [states, setStates] = useState<SharedTaskStateResponse[]>([]);
  const [selectedState, setSelectedState] =
    useState<SharedTaskStateResponse | null>(null);
  const [affinities, setAffinities] = useState<AffinityScoreResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"states" | "affinity">("states");

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [stateRes, affinityRes] = await Promise.all([
        getCognitiveStates(),
        getAffinityScores(),
      ]);
      setStates(stateRes.states);
      setAffinities(affinityRes.scores);
    } catch {
      // API may not be available
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSelectState = async (taskId: string) => {
    try {
      const state = await getCognitiveState(taskId);
      setSelectedState(state);
    } catch {
      // ignore
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/" className="text-sm text-text-muted hover:text-accent">
            Dashboard
          </Link>
          <h1 className="text-2xl font-bold">Unified Cognitive Layer</h1>
        </div>
        <button
          onClick={fetchData}
          disabled={loading}
          className="rounded bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent/80 disabled:opacity-50"
        >
          {loading ? "Loading..." : "Refresh"}
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-4 border-b border-border">
        <button
          onClick={() => {
            setTab("states");
            setSelectedState(null);
          }}
          className={`pb-2 text-sm ${
            tab === "states"
              ? "border-b-2 border-accent text-accent"
              : "text-text-muted hover:text-foreground"
          }`}
        >
          Shared States ({states.length})
        </button>
        <button
          onClick={() => setTab("affinity")}
          className={`pb-2 text-sm ${
            tab === "affinity"
              ? "border-b-2 border-accent text-accent"
              : "text-text-muted hover:text-foreground"
          }`}
        >
          Affinity Scores ({affinities.length})
        </button>
      </div>

      {/* Content */}
      {tab === "states" && (
        <>
          {selectedState ? (
            <StateDetail
              state={selectedState}
              onBack={() => setSelectedState(null)}
            />
          ) : states.length === 0 ? (
            <p className="text-sm text-text-muted">
              No active shared task states.
            </p>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {states.map((s) => (
                <StateCard
                  key={s.task_id}
                  state={s}
                  onSelect={handleSelectState}
                />
              ))}
            </div>
          )}
        </>
      )}

      {tab === "affinity" && <AffinityTable scores={affinities} />}
    </div>
  );
}
