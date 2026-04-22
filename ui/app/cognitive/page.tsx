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
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import StateCard from "./components/StateCard";
import StateDetail from "./components/StateDetail";
import AffinityTable from "./components/AffinityTable";

export default function CognitivePage() {
  const [states, setStates] = useState<SharedTaskStateResponse[]>([]);
  const [selectedState, setSelectedState] =
    useState<SharedTaskStateResponse | null>(null);
  const [affinities, setAffinities] = useState<AffinityScoreResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<string>("states");

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
          <Button variant="link" size="sm" asChild>
            <Link href="/">Dashboard</Link>
          </Button>
          <h1 className="text-lg font-semibold">Unified Cognitive Layer</h1>
        </div>
        <Button onClick={fetchData} disabled={loading}>
          {loading ? "Loading..." : "Refresh"}
        </Button>
      </div>

      {/* Tabs */}
      <Tabs
        value={tab}
        onValueChange={(v) => {
          setTab(v);
          if (v === "states") setSelectedState(null);
        }}
      >
        <TabsList>
          <TabsTrigger value="states">
            Shared States ({states.length})
          </TabsTrigger>
          <TabsTrigger value="affinity">
            Affinity Scores ({affinities.length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="states">
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
        </TabsContent>

        <TabsContent value="affinity">
          <AffinityTable scores={affinities} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
