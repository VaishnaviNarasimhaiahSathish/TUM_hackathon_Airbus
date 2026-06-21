import { useState, useEffect, useCallback } from 'react';
import { fetchSnapshot } from '../api/simulation';
import type { SimulationSnapshot } from '../api/simulation';

const POLL_MS = 1000;

export function useSimulation() {
  const [snapshot, setSnapshot] = useState<SimulationSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [paused, setPaused] = useState(false);
  const [manualTick, setManualTick] = useState<number | null>(null);

  const poll = useCallback(async () => {
    try {
      const data = await fetchSnapshot(manualTick ?? undefined);
      setSnapshot(data);
      setError(null);
      if (loading) setLoading(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'API unreachable');
      if (loading) setLoading(false);
    }
  }, [manualTick, loading]);

  useEffect(() => {
    poll();
    if (paused) return;
    const id = setInterval(poll, POLL_MS);
    return () => clearInterval(id);
  }, [poll, paused]);

  return {
    snapshot,
    error,
    loading,
    paused,
    setPaused,
    manualTick,
    setManualTick,
  };
}
