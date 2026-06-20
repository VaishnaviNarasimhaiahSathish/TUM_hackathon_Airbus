import { useEffect, useState } from 'react';
import { AIRCRAFT, ALERTS, EDGES, NODES, WEATHER_ZONES } from './worldData';
import type { DashboardSnapshot, WeatherZoneState } from '../types';

const API_URL = import.meta.env.VITE_SIMULATION_API_URL ?? '/api/simulation';

const fallbackSnapshot: DashboardSnapshot = {
  schema_version: 0,
  simulation: {
    tick: 0,
    tick_index: 0,
    simulation_seconds: 0,
    tick_seconds: 10,
    total_ticks: 1,
    replay_complete: false,
    source: 'frontend sample data (dashboard API unavailable)',
  },
  nodes: NODES,
  edges: EDGES,
  agents: AIRCRAFT,
  alerts: ALERTS,
  weather_zones: WEATHER_ZONES.map((zone) => ({
    ...zone,
    zone: zone.zone as WeatherZoneState['zone'],
    risk: zone.risk as WeatherZoneState['risk'],
    weather_risk: 0,
  })),
  metrics: {
    agent_count: AIRCRAFT.length,
    in_flight_count: AIRCRAFT.filter((aircraft) => aircraft.status === 'in_flight').length,
    emergency_count: AIRCRAFT.filter((aircraft) => aircraft.status === 'emergency').length,
    charging_count: AIRCRAFT.filter((aircraft) => aircraft.status === 'charging').length,
    average_battery_percent: Math.round(
      AIRCRAFT.reduce((sum, aircraft) => sum + aircraft.battery, 0) / AIRCRAFT.length,
    ),
    active_message_count: 0,
    active_reservation_count: 0,
  },
};

export function useDashboardSnapshot(): {
  dashboard: DashboardSnapshot;
  connected: boolean;
} {
  const [dashboard, setDashboard] = useState<DashboardSnapshot>(fallbackSnapshot);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let active = true;

    async function refresh(): Promise<void> {
      try {
        const response = await fetch(API_URL);
        if (!response.ok) {
          throw new Error(`Dashboard API responded with ${response.status}`);
        }
        const payload = (await response.json()) as DashboardSnapshot;
        if (active) {
          setDashboard(payload);
          setConnected(true);
        }
      } catch {
        if (active) {
          setConnected(false);
        }
      }
    }

    void refresh();
    const interval = window.setInterval(() => void refresh(), 1000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);

  return { dashboard, connected };
}
