import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts';
import type { AirNode, Aircraft, WeatherZoneState } from '../types';

interface AnalyticsPageProps {
  nodes: AirNode[];
  aircraft: Aircraft[];
  weatherZones: WeatherZoneState[];
}

const COLORS = ['#00b4ff', '#00e887', '#ffaa00', '#9b59ff', '#ff3355', '#ff6b35', '#00d4aa'];

const TOOLTIP_STYLE = {
  background: '#071428',
  border: '1px solid #1a3560',
  borderRadius: 6,
  fontSize: 12,
  color: '#e2f0ff',
};

export default function AnalyticsPage({
  nodes: NODES,
  aircraft: AIRCRAFT,
  weatherZones: WEATHER_ZONES,
}: AnalyticsPageProps) {
  const pads = NODES.filter(n => n.type === 'pad');
  const hospitals = NODES.filter(n => n.type === 'hospital');
  const chargers = NODES.filter(n => n.type === 'charging_hub');

  // Pad utilization data
  const padUtilData = pads.map(n => ({
    name: n.name.length > 16 ? n.name.slice(0, 14) + '…' : n.name,
    utilization: Math.round((n.current_load / n.capacity) * 100),
    capacity: n.capacity,
    load: n.current_load,
  }));

  // Zone type distribution
  const zoneCounts: Record<string, number> = {};
  NODES.forEach(n => { zoneCounts[n.zone_type] = (zoneCounts[n.zone_type] || 0) + 1; });
  const zonePieData = Object.entries(zoneCounts).map(([name, value]) => ({ name, value }));

  // Demand scores
  const demandData = [...NODES]
    .sort((a, b) => b.demand_score - a.demand_score)
    .slice(0, 10)
    .map(n => ({ name: n.name.length > 16 ? n.name.slice(0, 14) + '…' : n.name, demand: n.demand_score, type: n.type }));

  // Fleet status breakdown
  const statusCounts: Record<string, number> = {};
  AIRCRAFT.forEach(a => { statusCounts[a.status] = (statusCounts[a.status] || 0) + 1; });
  const fleetStatusData = Object.entries(statusCounts).map(([name, value]) => ({
    name: name.replace('_', ' '),
    value,
  }));

  const STATUS_COLORS: Record<string, string> = {
    'in flight': '#00b4ff',
    'charging': '#00e887',
    'at pad': '#9b59ff',
    'emergency': '#ff3355',
    'grounded': '#666',
  };

  const totalCapacity = NODES.reduce((s, n) => s + n.capacity, 0);
  const totalLoad = NODES.reduce((s, n) => s + n.current_load, 0);
  const avgDemand = Math.round(NODES.reduce((s, n) => s + n.demand_score, 0) / NODES.length);
  const avgBattery = Math.round(AIRCRAFT.reduce((s, a) => s + a.battery, 0) / AIRCRAFT.length);

  return (
    <div>
      <div className="page-title">Analytics</div>
      <div className="page-subtitle">Network performance · Demand · Fleet health</div>

      {/* KPI cards */}
      <div className="summary-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)', marginBottom: 20 }}>
        <div className="summary-card blue">
          <div className="summary-label">Network Utilization</div>
          <div className="summary-value">{Math.round((totalLoad / totalCapacity) * 100)}%</div>
          <div className="summary-sub">{totalLoad} / {totalCapacity} slots used</div>
        </div>
        <div className="summary-card green">
          <div className="summary-label">Avg Demand Score</div>
          <div className="summary-value">{avgDemand}</div>
          <div className="summary-sub">Across {NODES.length} nodes</div>
        </div>
        <div className="summary-card amber">
          <div className="summary-label">Avg Fleet Battery</div>
          <div className="summary-value">{avgBattery}%</div>
          <div className="summary-sub">{AIRCRAFT.filter(a=>a.battery<30).length} aircraft low</div>
        </div>
        <div className="summary-card purple">
          <div className="summary-label">Active Corridors</div>
          <div className="summary-value">{NODES.length}</div>
          <div className="summary-sub">{pads.length} pads · {hospitals.length} hospitals · {chargers.length} hubs</div>
        </div>
      </div>

      {/* Charts row 1 */}
      <div className="analytics-grid">
        <div className="card">
          <div className="card-header">
            <span className="card-title">Pad Utilization (%)</span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={padUtilData} margin={{ top: 4, right: 8, left: -20, bottom: 40 }}>
              <XAxis
                dataKey="name"
                tick={{ fill: '#3a6080', fontSize: 9 }}
                angle={-35}
                textAnchor="end"
                interval={0}
              />
              <YAxis tick={{ fill: '#3a6080', fontSize: 10 }} domain={[0, 100]} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                formatter={(v: number) => [`${v}%`, 'Utilization']}
              />
              <Bar dataKey="utilization" radius={[3, 3, 0, 0]}>
                {padUtilData.map((entry, i) => (
                  <Cell
                    key={i}
                    fill={entry.utilization >= 80 ? '#ff3355' : entry.utilization >= 50 ? '#ffaa00' : '#00e887'}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <div className="card-header">
            <span className="card-title">Zone Type Distribution</span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={zonePieData}
                cx="50%" cy="45%"
                outerRadius={70}
                dataKey="value"
                label={({ name, value }) => `${name} (${value})`}
                labelLine={false}
                fontSize={9}
              >
                {zonePieData.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={TOOLTIP_STYLE} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Charts row 2 */}
      <div className="analytics-grid">
        <div className="card">
          <div className="card-header">
            <span className="card-title">Top 10 Nodes by Demand Score</span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={demandData} layout="vertical" margin={{ top: 4, right: 16, left: 100, bottom: 4 }}>
              <XAxis type="number" tick={{ fill: '#3a6080', fontSize: 10 }} domain={[0, 100]} />
              <YAxis type="category" dataKey="name" tick={{ fill: '#6a9cc8', fontSize: 10 }} width={100} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Bar dataKey="demand" radius={[0, 3, 3, 0]}>
                {demandData.map((entry, i) => (
                  <Cell
                    key={i}
                    fill={entry.type === 'hospital' ? '#ff3355' : entry.type === 'charging_hub' ? '#00e887' : '#00b4ff'}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <div className="card-header">
            <span className="card-title">Fleet Status Breakdown</span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={fleetStatusData}
                cx="50%" cy="50%"
                innerRadius={45}
                outerRadius={75}
                dataKey="value"
                paddingAngle={3}
              >
                {fleetStatusData.map((entry, i) => (
                  <Cell key={i} fill={STATUS_COLORS[entry.name] || COLORS[i]} />
                ))}
              </Pie>
              <Legend
                iconSize={8}
                formatter={(value) => <span style={{ color: '#6a9cc8', fontSize: 11 }}>{value}</span>}
              />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Weather zones */}
      <div style={{ marginBottom: 20 }}>
        <div className="card-title" style={{ marginBottom: 12 }}>Weather Zone Status</div>
        <div className="weather-zone-row">
          {WEATHER_ZONES.map(z => (
            <div key={z.zone} className={`weather-chip ${z.risk}`}>
              <div className="weather-chip-zone">{z.zone}</div>
              <div className="weather-chip-cond">{z.condition}</div>
              <div style={{ fontSize: 9, color: 'var(--text-muted)' }}>
                {z.wind_kmh} km/h · {z.visibility_km} km vis
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Node summary table */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Full Node Summary</span>
          <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{NODES.length} nodes</span>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Name</th>
                <th>Type</th>
                <th>Status</th>
                <th>Load</th>
                <th>Priority</th>
                <th>Demand</th>
                <th>Zone</th>
                <th>Weather</th>
              </tr>
            </thead>
            <tbody>
              {NODES.map(n => (
                <tr key={n.id}>
                  <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', fontSize: 11 }}>{n.id}</td>
                  <td style={{ color: 'var(--text-primary)', fontSize: 12 }}>
                    {n.type === 'hospital' ? '🏥 ' : n.type === 'charging_hub' ? '⚡ ' : '◉ '}
                    {n.name}
                  </td>
                  <td style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{n.type.replace('_', ' ')}</td>
                  <td>
                    <span style={{
                      fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 10,
                      background: n.availability_status === 'available' ? 'rgba(0,232,135,0.1)'
                        : n.availability_status === 'busy' ? 'rgba(255,170,0,0.1)'
                        : 'rgba(255,51,85,0.1)',
                      color: n.availability_status === 'available' ? 'var(--green)'
                        : n.availability_status === 'busy' ? 'var(--amber)'
                        : 'var(--red)',
                      border: '1px solid',
                      borderColor: n.availability_status === 'available' ? 'var(--green-dim)'
                        : n.availability_status === 'busy' ? 'var(--amber-dim)'
                        : 'var(--red-dim)',
                    }}>
                      {n.availability_status}
                    </span>
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <div style={{ width: 40, height: 4, background: 'var(--border)', borderRadius: 2 }}>
                        <div style={{
                          width: `${(n.current_load / n.capacity) * 100}%`,
                          height: '100%',
                          background: n.availability_status === 'full' ? 'var(--red)' : n.availability_status === 'busy' ? 'var(--amber)' : 'var(--green)',
                          borderRadius: 2,
                        }} />
                      </div>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>
                        {n.current_load}/{n.capacity}
                      </span>
                    </div>
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: n.priority_level >= 9 ? 'var(--red)' : n.priority_level >= 7 ? 'var(--amber)' : 'var(--text-secondary)' }}>
                    {n.priority_level}/10
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent)' }}>{n.demand_score}</td>
                  <td style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{n.zone_type}</td>
                  <td style={{ fontSize: 11, color: 'var(--text-muted)' }}>{n.weather_zone}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
