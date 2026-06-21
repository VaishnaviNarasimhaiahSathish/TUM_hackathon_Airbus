import { useState, useMemo } from 'react';
import { MapContainer, TileLayer, Marker, Polyline, Popup } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { AirEdge, AirNode, Aircraft, SimulationState } from '../types';

interface VisualizationPageProps {
  nodes: AirNode[];
  edges: AirEdge[];
  aircraft: Aircraft[];
  simulation: SimulationState;
}

// ── Marker colors ──────────────────────────────────────────
function markerColor(node: AirNode): string {
  if (node.type === 'hospital') return '#e53935';
  if (node.type === 'charging_hub') {
    return node.availability_status === 'available' ? '#43a047'
      : node.availability_status === 'busy' ? '#fb8c00'
      : '#e53935';
  }
  // pad
  return node.availability_status === 'available' ? '#1e88e5'
    : node.availability_status === 'busy' ? '#fb8c00'
    : '#c62828';
}

function markerLetter(node: AirNode): string {
  if (node.type === 'hospital') return 'H';
  if (node.type === 'charging_hub') return 'C';
  return 'P';
}

function createIcon(node: AirNode, showLabel: boolean) {
  const color = markerColor(node);
  const letter = markerLetter(node);
  const size = node.type === 'hospital' ? 30 : 26;
  return L.divIcon({
    html: `<div style="
      background:${color};
      color:white;
      width:${size}px;height:${size}px;
      border-radius:50%;
      display:flex;align-items:center;justify-content:center;
      font-weight:800;font-size:12px;font-family:sans-serif;
      border:2px solid rgba(255,255,255,0.7);
      box-shadow:0 2px 8px rgba(0,0,0,0.5);
      position:relative;
    ">
      ${letter}
      ${showLabel ? `<span style="
        position:absolute;top:-18px;left:50%;transform:translateX(-50%);
        white-space:nowrap;font-size:9px;font-weight:700;
        background:rgba(10,20,40,0.85);color:#e2f0ff;
        padding:1px 5px;border-radius:3px;pointer-events:none;
        border:1px solid rgba(255,255,255,0.15);
      ">${node.name.length > 18 ? node.name.slice(0, 16) + '…' : node.name}</span>` : ''}
    </div>`,
    className: '',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function aircraftIcon(status: string) {
  const color = status === 'emergency' ? '#ff3355'
    : status === 'charging' ? '#00e887'
    : status === 'grounded' ? '#555'
    : '#00b4ff';
  return L.divIcon({
    html: `<div style="
      background:${color};
      color:white;
      width:20px;height:20px;
      border-radius:50%;
      display:flex;align-items:center;justify-content:center;
      font-size:10px;
      border:2px solid rgba(255,255,255,0.8);
      box-shadow:0 0 8px ${color};
    ">✈</div>`,
    className: '',
    iconSize: [20, 20],
    iconAnchor: [10, 10],
  });
}

// ── Corridor styles ──────────────────────────────────────────
const CORRIDOR_STYLES: Record<string, { color: string; weight: number; dashArray?: string; opacity: number }> = {
  airport_corridor:  { color: '#5c6bc0', weight: 3, opacity: 0.85 },
  city_corridor:     { color: '#ff08ff', weight: 2, opacity: 0.7 },
  medical_corridor:  { color: '#ef5350', weight: 2, dashArray: '6 5', opacity: 0.8 },
  charging_corridor: { color: '#26a69a', weight: 2, dashArray: '6 5', opacity: 0.75 },
};

const LOWEST_COST_STYLE = { color: '#ffd600', weight: 4, opacity: 0.95 };

// ── Layer checkbox labels ──────────────────────────────────────────
const LAYER_LABELS = [
  { key: 'airport',  label: 'Airport Corridors',        color: '#5c6bc0', dash: false },
  { key: 'city',     label: 'City Corridors',            color: '#ff08ff', dash: false },
  { key: 'medical',  label: 'Medical Corridors',         color: '#ef5350', dash: true },
  { key: 'charging', label: 'Charging Corridors',        color: '#26a69a', dash: true },
  { key: 'lowest',   label: 'Lowest-Cost Path',          color: '#ffd600', dash: false },
  { key: 'pads',     label: 'Pads',                      color: '#1e88e5', dash: false },
  { key: 'hospitals',label: 'Hospitals',                 color: '#e53935', dash: false },
  { key: 'hubs',     label: 'Charging Hubs',             color: '#43a047', dash: false },
  { key: 'aircraft', label: 'Aircraft',                  color: '#00b4ff', dash: false },
  { key: 'labels',   label: 'Location Labels',           color: '#aaa',    dash: false },
];

export default function VisualizationPage({
  nodes: NODES,
  edges: EDGES,
  aircraft: AIRCRAFT,
  simulation,
}: VisualizationPageProps) {
  const [layers, setLayers] = useState<Record<string, boolean>>({
    airport: true, city: true, medical: true, charging: true,
    lowest: true, pads: true, hospitals: true, hubs: true,
    aircraft: true, labels: false,
  });

  function toggle(key: string) {
    setLayers(prev => ({ ...prev, [key]: !prev[key] }));
  }

  // Lowest-cost edge
  const lowestEdge = useMemo(() => [...EDGES].sort((a, b) => a.total_cost - b.total_cost)[0], [EDGES]);

  // Node lookup by name
  function nodePos(name: string): [number, number] | null {
    const n = NODES.find(nd => nd.name === name);
    return n ? [n.lat, n.lon] : null;
  }

  // Stats for left panel
  const available = NODES.filter(n => n.availability_status === 'available').length;
  const busy = NODES.filter(n => n.availability_status === 'busy').length;
  const full = NODES.filter(n => n.availability_status === 'full').length;
  const pads = NODES.filter(n => n.type === 'pad');
  const hospitals = NODES.filter(n => n.type === 'hospital');
  const hubs = NODES.filter(n => n.type === 'charging_hub');
  const totalAircraft = EDGES.reduce((s, e) => s + e.current_aircraft_count, 0);
  const replayLabel = `T+${simulation.simulation_seconds}s`;

  const panelStyle: React.CSSProperties = {
    position: 'absolute',
    zIndex: 1000,
    background: 'rgba(7,20,40,0.94)',
    border: '1px solid #1a3560',
    borderRadius: 8,
    color: '#e2f0ff',
    fontFamily: 'Inter, system-ui, sans-serif',
    fontSize: 12,
    backdropFilter: 'blur(8px)',
  };

  return (
    <div style={{ flex: 1, position: 'relative', overflow: 'hidden', height: '100%' }}>
      <MapContainer
        center={[48.17, 11.6]}
        zoom={11}
        style={{ height: '100%', width: '100%' }}
        zoomControl={false}
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; OpenStreetMap contributors'
        />

        {/* Corridors */}
        {EDGES.map((edge, i) => {
          const from = nodePos(edge.start);
          const to = nodePos(edge.end);
          if (!from || !to) return null;
          const type = edge.route_type;
          const layerKey =
            type === 'airport_corridor' ? 'airport' :
            type === 'city_corridor' ? 'city' :
            type === 'medical_corridor' ? 'medical' : 'charging';
          if (!layers[layerKey]) return null;
          const style = CORRIDOR_STYLES[type] ?? { color: '#aaa', weight: 1, opacity: 0.5 };
          return (
            <Polyline
              key={`edge-${i}`}
              positions={[from, to]}
              pathOptions={{ color: style.color, weight: style.weight, dashArray: style.dashArray, opacity: style.opacity }}
            >
              <Popup>
                <div style={{ fontFamily: 'sans-serif', fontSize: 12 }}>
                  <div style={{ fontWeight: 700, color: style.color, marginBottom: 4 }}>
                    {edge.start} → {edge.end}
                  </div>
                  <div>Type: {type.replace('_', ' ')}</div>
                  <div>Distance: {edge.distance_km} km</div>
                  <div>Aircraft: {edge.current_aircraft_count}</div>
                  <div>Traffic penalty: {edge.traffic_penalty}</div>
                  <div>Total cost: {edge.total_cost}</div>
                </div>
              </Popup>
            </Polyline>
          );
        })}

        {/* Lowest-cost path highlight */}
        {layers.lowest && (() => {
          const from = nodePos(lowestEdge.start);
          const to = nodePos(lowestEdge.end);
          if (!from || !to) return null;
          return (
            <Polyline
              positions={[from, to]}
              pathOptions={{ ...LOWEST_COST_STYLE, dashArray: undefined }}
            >
              <Popup>
                <div style={{ fontFamily: 'sans-serif', fontSize: 12 }}>
                  <div style={{ fontWeight: 700, color: '#ffd600', marginBottom: 4 }}>
                    ⭐ Lowest-Cost Path
                  </div>
                  <div>{lowestEdge.start} → {lowestEdge.end}</div>
                  <div>Total cost: {lowestEdge.total_cost}</div>
                </div>
              </Popup>
            </Polyline>
          );
        })()}

        {/* Pad markers */}
        {layers.pads && pads.map(node => (
          <Marker key={node.id} position={[node.lat, node.lon]} icon={createIcon(node, layers.labels)}>
            <Popup>
              <div style={{ fontFamily: 'sans-serif', fontSize: 12 }}>
                <div style={{ fontWeight: 700, color: markerColor(node), marginBottom: 4 }}>{node.name}</div>
                <div>Status: <b>{node.availability_status}</b></div>
                <div>Load: {node.current_load}/{node.capacity}</div>
                <div>Zone: {node.zone_type}</div>
                <div>Priority: {node.priority_level}/10</div>
                <div>Demand: {node.demand_score}</div>
              </div>
            </Popup>
          </Marker>
        ))}

        {/* Hospital markers */}
        {layers.hospitals && hospitals.map(node => (
          <Marker key={node.id} position={[node.lat, node.lon]} icon={createIcon(node, layers.labels)}>
            <Popup>
              <div style={{ fontFamily: 'sans-serif', fontSize: 12 }}>
                <div style={{ fontWeight: 700, color: '#e53935', marginBottom: 4 }}>🏥 {node.name}</div>
                <div>Status: <b>{node.availability_status}</b></div>
                <div>Load: {node.current_load}/{node.capacity}</div>
                <div>Priority: {node.priority_level}/10 (medical)</div>
              </div>
            </Popup>
          </Marker>
        ))}

        {/* Charging hub markers */}
        {layers.hubs && hubs.map(node => (
          <Marker key={node.id} position={[node.lat, node.lon]} icon={createIcon(node, layers.labels)}>
            <Popup>
              <div style={{ fontFamily: 'sans-serif', fontSize: 12 }}>
                <div style={{ fontWeight: 700, color: markerColor(node), marginBottom: 4 }}>⚡ {node.name}</div>
                <div>Status: <b>{node.availability_status}</b></div>
                <div>Load: {node.current_load}/{node.capacity}</div>
                <div>Zone: {node.weather_zone}</div>
              </div>
            </Popup>
          </Marker>
        ))}

        {/* Aircraft */}
        {layers.aircraft && AIRCRAFT.map(ac => (
          <Marker key={ac.id} position={[ac.lat, ac.lon]} icon={aircraftIcon(ac.status)}>
            <Popup>
              <div style={{ fontFamily: 'sans-serif', fontSize: 12 }}>
                <div style={{ fontWeight: 700, color: '#00b4ff', marginBottom: 4 }}>✈ {ac.id}</div>
                <div>Status: <b style={{ color: ac.status === 'emergency' ? '#ff3355' : undefined }}>{ac.status}</b></div>
                <div>Mission: {ac.mission}</div>
                <div>Battery: <b style={{ color: ac.battery < 30 ? '#ff3355' : ac.battery < 60 ? '#fb8c00' : '#00e887' }}>{ac.battery}%</b></div>
                <div>{ac.from} → {ac.to}</div>
                {ac.altitude_m > 0 && <div>Alt: {ac.altitude_m} m · {ac.speed_kmh} km/h</div>}
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>

      {/* ── LEFT INFO PANEL ── */}
      <div style={{ ...panelStyle, top: 12, left: 12, width: 210, padding: '14px 16px' }}>
        <div style={{ fontWeight: 800, fontSize: 13, color: '#00b4ff', marginBottom: 2 }}>
          Munich Airspace Digital Twin
        </div>
        <div style={{ fontSize: 10, color: '#3a6080', marginBottom: 12, textTransform: 'uppercase', letterSpacing: 1 }}>
          Layer 3: Shared environment
        </div>

        {/* Availability row */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 4, marginBottom: 12 }}>
          {[
            { count: available, label: 'Available', bg: 'rgba(30,136,229,0.15)', border: '#1e88e5', color: '#64b5f6' },
            { count: busy, label: 'Busy', bg: 'rgba(251,140,0,0.15)', border: '#fb8c00', color: '#ffb74d' },
            { count: full, label: 'Full', bg: 'rgba(198,40,40,0.15)', border: '#c62828', color: '#ef9a9a' },
          ].map(s => (
            <div key={s.label} style={{ background: s.bg, border: `1px solid ${s.border}`, borderRadius: 6, padding: '6px 4px', textAlign: 'center' }}>
              <div style={{ fontSize: 20, fontWeight: 800, color: s.color, lineHeight: 1, fontFamily: 'monospace' }}>{s.count}</div>
              <div style={{ fontSize: 9, color: '#6a9cc8', marginTop: 2, textTransform: 'uppercase', letterSpacing: 0.5 }}>{s.label}</div>
            </div>
          ))}
        </div>

        {/* Node counts */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, marginBottom: 12 }}>
          {[
            { count: pads.length, label: 'Pads' },
            { count: hospitals.length, label: 'Hospitals' },
            { count: hubs.length, label: 'Charging Hubs' },
            { count: totalAircraft, label: 'On Routes' },
          ].map(s => (
            <div key={s.label} style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid #1a3560', borderRadius: 5, padding: '5px 8px' }}>
              <div style={{ fontSize: 18, fontWeight: 700, color: '#e2f0ff', fontFamily: 'monospace' }}>{s.count}</div>
              <div style={{ fontSize: 9, color: '#3a6080', textTransform: 'uppercase', letterSpacing: 0.5 }}>{s.label}</div>
            </div>
          ))}
        </div>

        {/* Formulas */}
        <div style={{ borderTop: '1px solid #1a3560', paddingTop: 10, marginBottom: 10 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: '#6a9cc8', marginBottom: 3 }}>Cost formula</div>
          <div style={{ fontSize: 10, color: '#3a6080' }}>distance + battery + noise + weather + traffic</div>
        </div>
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: '#6a9cc8', marginBottom: 3 }}>Battery</div>
          <div style={{ fontSize: 10, color: '#3a6080' }}>battery cost = distance × 0.18</div>
        </div>
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: '#6a9cc8', marginBottom: 3 }}>Traffic</div>
          <div style={{ fontSize: 10, color: '#3a6080' }}>penalty = aircraft count × 2.0</div>
        </div>

        {/* Marker legend */}
        <div style={{ borderTop: '1px solid #1a3560', paddingTop: 10 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: '#6a9cc8', marginBottom: 6 }}>Marker colors</div>
          {[
            { color: '#1e88e5', label: 'Available pad' },
            { color: '#fb8c00', label: 'Busy / low slots' },
            { color: '#c62828', label: 'Full / no slots' },
            { color: '#e53935', label: 'Hospital' },
            { color: '#43a047', label: 'Charging hub' },
            { color: '#00b4ff', label: 'Aircraft' },
          ].map(l => (
            <div key={l.label} style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 4 }}>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: l.color, flexShrink: 0 }} />
              <span style={{ fontSize: 10, color: '#6a9cc8' }}>{l.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── RIGHT LAYER CONTROLS ── */}
      <div style={{ ...panelStyle, top: 12, right: 12, padding: '12px 14px', minWidth: 210 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: '#6a9cc8', textTransform: 'uppercase', letterSpacing: 1.5 }}>
            Layers
          </div>
          <div style={{ display: 'flex', gap: 4 }}>
            <button
              onClick={() => setLayers(Object.fromEntries(LAYER_LABELS.map(l => [l.key, true])))}
              style={{
                fontSize: 9, fontWeight: 700, padding: '2px 7px', borderRadius: 4, cursor: 'pointer',
                background: 'rgba(0,180,255,0.1)', border: '1px solid #0077aa', color: '#00b4ff',
                letterSpacing: 0.5, textTransform: 'uppercase',
              }}
            >All</button>
            <button
              onClick={() => setLayers(Object.fromEntries(LAYER_LABELS.map(l => [l.key, false])))}
              style={{
                fontSize: 9, fontWeight: 700, padding: '2px 7px', borderRadius: 4, cursor: 'pointer',
                background: 'rgba(255,255,255,0.04)', border: '1px solid #1a3560', color: '#3a6080',
                letterSpacing: 0.5, textTransform: 'uppercase',
              }}
            >None</button>
          </div>
        </div>
        <div style={{ fontSize: 10, color: '#3a6080', marginBottom: 10 }}>
          {replayLabel} · tick {simulation.tick}
        </div>
        {LAYER_LABELS.map(l => (
          <label key={l.key} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 7, cursor: 'pointer', userSelect: 'none' }}>
            <input
              type="checkbox"
              checked={layers[l.key]}
              onChange={() => toggle(l.key)}
              style={{ accentColor: l.color, width: 13, height: 13 }}
            />
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1 }}>
              {l.dash ? (
                <div style={{ width: 18, height: 2, borderTop: `2px dashed ${l.color}`, flexShrink: 0 }} />
              ) : (
                <div style={{ width: 18, height: 3, background: l.color, borderRadius: 1, flexShrink: 0 }} />
              )}
              <span style={{ fontSize: 11, color: layers[l.key] ? '#e2f0ff' : '#3a6080', transition: 'color 0.15s' }}>
                {l.label}
              </span>
            </div>
          </label>
        ))}
      </div>

      {/* ── ZOOM CONTROLS (bottom-left) ── */}
      <div style={{ ...panelStyle, bottom: 30, left: 12, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Built-in zoom is disabled, using custom */}
      </div>
    </div>
  );
}
