const BASE = 'http://127.0.0.1:8000';

export interface SimulationInfo {
  tick: number;
  tick_index: number;
  simulation_seconds: number;
  tick_seconds: number;
  total_ticks: number;
  replay_complete: boolean;
  source: string;
}

export interface ApiNode {
  id: number;
  name: string;
  type: 'pad' | 'hospital' | 'charging_hub';
  lat: number;
  lon: number;
  description: string;
  capacity: number;
  current_load: number;
  available_slots: number;
  availability_status: 'available' | 'busy' | 'full';
  priority_level: number;
  zone_type: string;
  demand_score: number;
  weather_zone: string;
  charging_available: boolean;
  emergency_landing: boolean;
}

export interface ApiEdge {
  start: string;
  end: string;
  route_type: string;
  distance_km: number;
  battery_cost: number;
  noise_penalty: number;
  noise_level: number;
  weather_penalty: number;
  weather_risk: number;
  blocked: boolean;
  current_aircraft_count: number;
  active_agent_ids: string[];
  traffic_density: number;
  traffic_penalty: number;
  total_cost: number;
}

export interface ApiAgent {
  id: string;
  evtol_id: string;
  status: 'in_flight' | 'charging' | 'at_pad' | 'emergency' | 'grounded';
  operational_status: string;
  battery: number;
  mission: string;
  from: string;
  to: string;
  progress: number;
  lat: number;
  lon: number;
  altitude_m: number;
  speed_kmh: number;
  current_node: string | null;
  target_node: string | null;
  decision_reason: string;
  health_status: string;
  neighbor_count: number;
  current_edge: [string, string] | null;
  current_route: string[];
  estimated_arrival_tick: number | null;
}

export interface ApiAlert {
  id: string;
  level: 'info' | 'warning' | 'critical';
  message: string;
  time: string;
}

export interface ApiWeatherZone {
  zone: string;
  condition: string;
  risk: 'low' | 'medium' | 'high';
  weather_risk: number;
  wind_kmh: number;
  visibility_km: number;
}

export interface ApiMetrics {
  agent_count: number;
  in_flight_count: number;
  emergency_count: number;
  charging_count: number;
  average_battery_percent: number;
  active_message_count: number;
  active_reservation_count: number;
}

export interface SimulationSnapshot {
  schema_version: number;
  simulation: SimulationInfo;
  nodes: ApiNode[];
  edges: ApiEdge[];
  agents: ApiAgent[];
  alerts: ApiAlert[];
  weather_zones: ApiWeatherZone[];
  metrics: ApiMetrics;
}

export async function fetchSnapshot(tick?: number): Promise<SimulationSnapshot> {
  const url = tick !== undefined
    ? `${BASE}/api/simulation?tick=${tick}`
    : `${BASE}/api/simulation`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}
