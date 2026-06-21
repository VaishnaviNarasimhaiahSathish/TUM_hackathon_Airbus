export type NodeType = 'pad' | 'hospital' | 'charging_hub';
export type AvailabilityStatus = 'available' | 'busy' | 'full';
export type ZoneType = 'airport' | 'commercial' | 'educational' | 'event' | 'residential' | 'medical' | 'mixed';
export type WeatherZone = 'north' | 'central' | 'east' | 'west' | 'south' | 'southeast' | 'northwest';

export interface AirNode {
  id: number;
  name: string;
  type: NodeType;
  lat: number;
  lon: number;
  description: string;
  capacity: number;
  current_load: number;
  available_slots: number;
  availability_status: AvailabilityStatus;
  priority_level: number;
  zone_type: ZoneType;
  demand_score: number;
  weather_zone: WeatherZone;
  charging_available?: boolean;
  emergency_landing?: boolean;
}

export interface AirEdge {
  start: string;
  end: string;
  route_type: string;
  distance_km: number;
  battery_consumption_rate: number;
  battery_cost: number;
  noise_penalty: number;
  weather_penalty: number;
  current_aircraft_count: number;
  traffic_penalty_per_aircraft: number;
  traffic_penalty: number;
  total_cost: number;
  traffic_density?: number;
  noise_level?: number;
  weather_risk?: number;
  blocked?: boolean;
  active_agent_ids?: string[];
}

export type AircraftStatus = 'in_flight' | 'charging' | 'at_pad' | 'emergency' | 'grounded';
export type MissionType =
  | 'Passenger'
  | 'Medical'
  | 'Cargo'
  | 'Emergency'
  | 'Autonomous Transit'
  | 'Charging Diversion'
  | 'Emergency Response'
  | 'Technical Failure'
  | 'Battery Recovery';

export interface Aircraft {
  id: string;
  status: AircraftStatus;
  battery: number;
  mission: MissionType;
  from: string;
  to: string;
  progress: number;
  lat: number;
  lon: number;
  altitude_m: number;
  speed_kmh: number;
  evtol_id?: string;
  operational_status?: string;
  current_node?: string;
  target_node?: string | null;
  assigned_origin?: string | null;
  assigned_destination?: string | null;
  mission_target?: string | null;
  mission_type?: string;
  cargo_description?: string | null;
  current_edge?: [string, string] | null;
  current_route?: string[];
  estimated_arrival_tick?: number | null;
  health_status?: string;
  emergency_reason?: string | null;
  neighbor_count?: number;
  communication_neighbors?: Array<Record<string, unknown>>;
  local_traffic_view?: Record<string, number>;
  local_noise_view?: Record<string, number>;
  local_weather_view?: Record<string, number>;
  local_vertiport_queue_view?: Record<string, number>;
  route_cost_breakdown?: Record<string, number>;
  decision_reason?: string;
}

export type TabId = 'monitoring' | 'visualization' | 'emergency' | 'analytics';

export interface Alert {
  id: string;
  level: 'info' | 'warning' | 'critical';
  message: string;
  time: string;
}

export interface WeatherZoneState {
  zone: WeatherZone;
  condition: string;
  risk: 'low' | 'medium' | 'high';
  weather_risk: number;
  wind_kmh: number;
  visibility_km: number;
}

export interface SimulationState {
  tick: number;
  tick_index: number;
  simulation_seconds: number;
  tick_seconds: number;
  total_ticks: number;
  replay_complete: boolean;
  source: string;
}

export interface DashboardMetrics {
  agent_count: number;
  in_flight_count: number;
  emergency_count: number;
  charging_count: number;
  average_battery_percent: number;
  active_message_count: number;
  active_reservation_count: number;
}

export interface DashboardSnapshot {
  schema_version: number;
  simulation: SimulationState;
  nodes: AirNode[];
  edges: AirEdge[];
  agents: Aircraft[];
  alerts: Alert[];
  weather_zones: WeatherZoneState[];
  metrics: DashboardMetrics;
}
