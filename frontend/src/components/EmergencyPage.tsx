import { useState } from 'react';
import type { Aircraft, Alert } from '../types';

interface EmergencyPageProps {
  aircraft: Aircraft[];
  alerts: Alert[];
}

interface LogEntry {
  time: string;
  text: string;
  type: 'action' | 'system' | 'alert';
}

const INITIAL_LOG: LogEntry[] = [
  { time: '14:31:02', text: 'SYSTEM: AC-004 battery critical — emergency landing triggered', type: 'alert' },
  { time: '14:28:47', text: 'SYSTEM: AC-011 grounded at Olympiapark — battery depleted', type: 'alert' },
  { time: '14:25:00', text: 'SYSTEM: Weather alert issued for southeast zone', type: 'system' },
  { time: '14:20:00', text: 'SYSTEM: Normal operations resumed in north corridor', type: 'system' },
  { time: '14:15:00', text: 'OPERATOR: Manual check completed — all hospital pads confirmed', type: 'action' },
];

export default function EmergencyPage({
  aircraft: AIRCRAFT,
  alerts: ALERTS,
}: EmergencyPageProps) {
  const [log, setLog] = useState<LogEntry[]>(INITIAL_LOG);
  const [activeOverrides, setActiveOverrides] = useState<Set<string>>(new Set());

  const now = () => new Date().toLocaleTimeString('en-GB');

  function triggerAction(key: string, text: string) {
    const newActive = new Set(activeOverrides);
    if (newActive.has(key)) {
      newActive.delete(key);
      setLog(prev => [{ time: now(), text: `OPERATOR: ${text} — DEACTIVATED`, type: 'action' }, ...prev]);
    } else {
      newActive.add(key);
      setLog(prev => [{ time: now(), text: `OPERATOR: ${text} — ACTIVATED`, type: 'action' }, ...prev]);
    }
    setActiveOverrides(newActive);
  }

  const criticalAircraft = AIRCRAFT.filter(a => a.status === 'emergency' || a.status === 'grounded');
  const criticalAlerts = ALERTS.filter(a => a.level === 'critical');

  return (
    <div>
      <div className="page-title" style={{ color: 'var(--red)' }}>Emergency Override</div>
      <div className="page-subtitle">Manual intervention controls · Layer 1 authority only</div>

      {/* Banner */}
      <div className="emergency-banner">
        <span style={{ fontSize: 28 }}>⚠</span>
        <div>
          <div className="emergency-banner-title">
            {criticalAircraft.length} Aircraft Require Attention
          </div>
          <div className="emergency-banner-sub">
            {criticalAircraft.map(a => a.id).join(', ')} · Immediate action may be required
          </div>
        </div>
        <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 1 }}>Override Level</div>
          <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--red)', fontFamily: 'var(--font-mono)' }}>
            {activeOverrides.size > 0 ? `L1-ACTIVE (${activeOverrides.size})` : 'STANDBY'}
          </div>
        </div>
      </div>

      {/* Action buttons */}
      <div className="emergency-actions">
        <button
          className={`emergency-btn red${activeOverrides.has('ground_all') ? ' active' : ''}`}
          onClick={() => triggerAction('ground_all', 'Ground All Aircraft issued')}
          style={activeOverrides.has('ground_all') ? { boxShadow: '0 0 20px rgba(255,51,85,0.4)' } : {}}
        >
          <div className="emergency-btn-icon">🛑</div>
          <div>
            <div className="emergency-btn-title">
              {activeOverrides.has('ground_all') ? '✓ GROUNDING ACTIVE' : 'Ground All Aircraft'}
            </div>
            <div className="emergency-btn-desc">
              Issue fleet-wide ground command. All in-flight aircraft divert to nearest available pad. Overrides autonomous decisions.
            </div>
          </div>
        </button>

        <button
          className={`emergency-btn amber${activeOverrides.has('hospital_priority') ? ' active' : ''}`}
          onClick={() => triggerAction('hospital_priority', 'Hospital Priority Mode issued')}
          style={activeOverrides.has('hospital_priority') ? { boxShadow: '0 0 20px rgba(255,170,0,0.3)' } : {}}
        >
          <div className="emergency-btn-icon">🏥</div>
          <div>
            <div className="emergency-btn-title">
              {activeOverrides.has('hospital_priority') ? '✓ HOSPITAL PRIORITY ACTIVE' : 'Hospital Priority Mode'}
            </div>
            <div className="emergency-btn-desc">
              Reserve all hospital landing pads for medical and emergency missions only. Non-critical aircraft denied approach.
            </div>
          </div>
        </button>

        <button
          className={`emergency-btn blue${activeOverrides.has('clear_corridors') ? ' active' : ''}`}
          onClick={() => triggerAction('clear_corridors', 'Clear All Corridors issued')}
          style={activeOverrides.has('clear_corridors') ? { boxShadow: '0 0 20px rgba(0,180,255,0.3)' } : {}}
        >
          <div className="emergency-btn-icon">✈</div>
          <div>
            <div className="emergency-btn-title">
              {activeOverrides.has('clear_corridors') ? '✓ CORRIDORS CLEARED' : 'Clear All Corridors'}
            </div>
            <div className="emergency-btn-desc">
              Remove all aircraft from active corridors. Creates emergency transit windows for priority missions across Munich.
            </div>
          </div>
        </button>

        <button
          className={`emergency-btn green${activeOverrides.has('restore') ? ' active' : ''}`}
          onClick={() => {
            setActiveOverrides(new Set());
            setLog(prev => [{ time: now(), text: 'OPERATOR: Restore Normal Operations — all overrides cleared', type: 'action' }, ...prev]);
          }}
        >
          <div className="emergency-btn-icon">✅</div>
          <div>
            <div className="emergency-btn-title">Restore Normal Operations</div>
            <div className="emergency-btn-desc">
              Deactivate all manual overrides. Return full autonomous control to distributed aircraft agents (Layer 2).
            </div>
          </div>
        </button>
      </div>

      {/* Active incidents + log */}
      <div className="two-col">
        <div className="card">
          <div className="card-header">
            <span className="card-title">Active Incidents</span>
            <span style={{ fontSize: 10, color: 'var(--red)' }}>{criticalAlerts.length} critical</span>
          </div>
          {criticalAircraft.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: 12, textAlign: 'center', padding: '20px 0' }}>
              No active incidents
            </div>
          ) : (
            criticalAircraft.map(ac => (
              <div key={ac.id} style={{
                padding: '10px',
                marginBottom: 8,
                background: 'var(--red-glow)',
                border: '1px solid var(--red-dim)',
                borderRadius: 6,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--red)', fontWeight: 700 }}>{ac.id}</span>
                  <span className={`badge ${ac.status}`}>{ac.status.replace('_', ' ')}</span>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                  Battery: <span style={{ color: 'var(--red)', fontFamily: 'var(--font-mono)' }}>{ac.battery}%</span>
                  {' · '}Mission: {ac.mission}
                  {' · '}Location: {ac.from}
                </div>
                {ac.emergency_reason && (
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>
                    Incident: <span style={{ color: 'var(--red)' }}>{ac.emergency_reason.replace('_', ' ')}</span>
                  </div>
                )}
              </div>
            ))
          )}

          <div style={{ marginTop: 12 }}>
            <div className="card-title" style={{ marginBottom: 8 }}>Critical Alerts</div>
            {criticalAlerts.map(a => (
              <div key={a.id} className="alert-item">
                <div className="alert-dot critical" />
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
            <span className="card-title">Override Log</span>
            <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>Most recent first</span>
          </div>
          <div style={{ maxHeight: 350, overflowY: 'auto' }}>
            {log.map((entry, i) => (
              <div key={i} className="log-entry">
                <span className="log-time">{entry.time}</span>
                <span className="log-text" style={{
                  color: entry.type === 'action' ? 'var(--amber)'
                    : entry.type === 'alert' ? 'var(--red)'
                    : 'var(--text-secondary)',
                }}>
                  {entry.text}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
