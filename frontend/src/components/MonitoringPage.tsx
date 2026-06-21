import type { AirNode, Aircraft, Alert, SimulationState } from '../types';

interface MonitoringPageProps {
  nodes: AirNode[];
  aircraft: Aircraft[];
  alerts: Alert[];
  simulation: SimulationState;
}

function BatteryBar({ value }: { value: number }) {
  const cls = value >= 60 ? 'high' : value >= 30 ? 'mid' : 'low';
  return (
    <div className="battery-bar">
      <div className="battery-track">
        <div className={`battery-fill ${cls}`} style={{ width: `${value}%` }} />
      </div>
      <span className="battery-text" style={{ color: cls === 'high' ? 'var(--green)' : cls === 'mid' ? 'var(--amber)' : 'var(--red)' }}>
        {value}%
      </span>
    </div>
  );
}

function StatusBadge({ status }: { status: Aircraft['status'] }) {
  const labels: Record<Aircraft['status'], string> = {
    in_flight: 'In Flight',
    charging: 'Charging',
    at_pad: 'At Pad',
    emergency: 'EMERGENCY',
    grounded: 'Grounded',
  };
  return <span className={`badge ${status}`}>{labels[status]}</span>;
}

function MissionBadge({ mission }: { mission: Aircraft['mission'] }) {
  const cls = mission === 'Medical' ? 'medical' : mission === 'Emergency' || mission === 'Technical Failure' || mission === 'Battery Recovery' ? 'emergency' : mission === 'Cargo' ? 'cargo' : 'passenger';
  return <span className={`badge ${cls}`}>{mission}</span>;
}

export default function MonitoringPage({
  nodes: NODES,
  aircraft: AIRCRAFT,
  alerts: ALERTS,
  simulation,
}: MonitoringPageProps) {
  const inFlight = AIRCRAFT.filter(a => a.status === 'in_flight').length;
  const charging = AIRCRAFT.filter(a => a.status === 'charging').length;
  const grounded = AIRCRAFT.filter(a => a.status === 'grounded').length;
  const emergency = AIRCRAFT.filter(a => a.status === 'emergency').length;
  const replayTime = `T+${simulation.simulation_seconds}s`;

  const pads = NODES.filter(n => n.type === 'pad');
  const hospitals = NODES.filter(n => n.type === 'hospital');
  const chargers = NODES.filter(n => n.type === 'charging_hub');
  const availablePads = pads.filter(n => n.availability_status === 'available').length;

  return (
    <div>
      <div className="page-title">Fleet Monitoring</div>
      <div className="page-subtitle">Real-time status · 12 aircraft · Munich UAM Network</div>

      {/* Summary cards */}
      <div className="summary-grid">
        <div className="summary-card blue">
          <div className="summary-label">Total Fleet</div>
          <div className="summary-value">{AIRCRAFT.length}</div>
          <div className="summary-sub">{inFlight} in flight right now</div>
        </div>
        <div className="summary-card green">
          <div className="summary-label">Active Missions</div>
          <div className="summary-value">{inFlight}</div>
          <div className="summary-sub">{charging} charging · {AIRCRAFT.filter(a=>a.status==='at_pad').length} at pad</div>
        </div>
        <div className="summary-card amber">
          <div className="summary-label">Pads Available</div>
          <div className="summary-value">{availablePads}</div>
          <div className="summary-sub">of {pads.length} total pads</div>
        </div>
        <div className="summary-card red">
          <div className="summary-label">Alerts</div>
          <div className="summary-value">{emergency + grounded}</div>
          <div className="summary-sub">{emergency} emergency · {grounded} grounded</div>
        </div>
      </div>

      {/* Alerts + Pad Grid */}
      <div className="sixty-forty">
        <div className="card">
          <div className="card-header">
            <span className="card-title">Live Alerts</span>
            <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{ALERTS.length} events | {replayTime}</span>
          </div>
          <div style={{ maxHeight: 220, overflowY: 'auto' }}>
            {ALERTS.map(a => (
              <div key={a.id} className="alert-item">
                <div className={`alert-dot ${a.level}`} />
                <div>
                  <div className="alert-text">{a.message}</div>
                  <div className="alert-time">{a.time}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <span className="card-title">Pad Occupancy</span>
          </div>
          <div className="pad-grid">
            {pads.map(n => (
              <div key={n.id} className="pad-cell">
                <div className="pad-cell-name">{n.name}</div>
                <div className="pad-bar-track">
                  <div
                    className={`pad-bar-fill ${n.availability_status}`}
                    style={{ width: `${(n.current_load / n.capacity) * 100}%` }}
                  />
                </div>
                <div className="pad-load-text">{n.current_load}/{n.capacity}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Infrastructure row */}
      <div className="two-col" style={{ marginBottom: 20 }}>
        <div className="card">
          <div className="card-header">
            <span className="card-title">Hospitals</span>
            <span style={{ fontSize: 10, color: 'var(--green)' }}>
              {hospitals.filter(h => h.availability_status === 'available').length} available
            </span>
          </div>
          <div className="pad-grid">
            {hospitals.map(h => (
              <div key={h.id} className="pad-cell">
                <div className="pad-cell-name">🏥 {h.name}</div>
                <div className="pad-bar-track">
                  <div
                    className={`pad-bar-fill ${h.availability_status}`}
                    style={{ width: `${(h.current_load / h.capacity) * 100}%` }}
                  />
                </div>
                <div className="pad-load-text">{h.current_load}/{h.capacity}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <span className="card-title">Charging Hubs</span>
            <span style={{ fontSize: 10, color: 'var(--green)' }}>
              {chargers.filter(c => c.availability_status === 'available').length} available
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {chargers.map(c => (
              <div key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: 10, color: 'var(--text-secondary)', width: 160, flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  ⚡ {c.name}
                </span>
                <div className="pad-bar-track" style={{ flex: 1 }}>
                  <div
                    className={`pad-bar-fill ${c.availability_status}`}
                    style={{ width: `${(c.current_load / c.capacity) * 100}%` }}
                  />
                </div>
                <span className="pad-load-text">{c.current_load}/{c.capacity}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Aircraft table */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Fleet Status Table</span>
          <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>All aircraft</span>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Status</th>
                <th>Mission</th>
                <th>Battery</th>
                <th>From</th>
                <th>To</th>
                <th>Progress</th>
                <th>Alt (m)</th>
                <th>Speed</th>
              </tr>
            </thead>
            <tbody>
              {AIRCRAFT.map(ac => (
                <tr key={ac.id}>
                  <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)', fontWeight: 600 }}>{ac.id}</td>
                  <td><StatusBadge status={ac.status} /></td>
                  <td><MissionBadge mission={ac.mission} /></td>
                  <td><BatteryBar value={ac.battery} /></td>
                  <td style={{ color: 'var(--text-secondary)', fontSize: 11 }}>{ac.from}</td>
                  <td style={{ color: 'var(--text-secondary)', fontSize: 11 }}>{ac.to}</td>
                  <td>
                    {ac.status === 'in_flight' || ac.status === 'emergency' ? (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div style={{ width: 48, height: 4, background: 'var(--border)', borderRadius: 2 }}>
                          <div style={{ width: `${ac.progress * 100}%`, height: '100%', background: ac.status === 'emergency' ? 'var(--red)' : 'var(--accent)', borderRadius: 2 }} />
                        </div>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>
                          {Math.round(ac.progress * 100)}%
                        </span>
                      </div>
                    ) : <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>—</span>}
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: ac.altitude_m === 0 ? 'var(--text-muted)' : 'var(--text-primary)' }}>
                    {ac.altitude_m || '—'}
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: ac.speed_kmh === 0 ? 'var(--text-muted)' : 'var(--text-primary)' }}>
                    {ac.speed_kmh ? `${ac.speed_kmh} km/h` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
