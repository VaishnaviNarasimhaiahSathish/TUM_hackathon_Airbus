import type { Aircraft, TabId } from '../types';

interface SidebarProps {
  active: TabId;
  onSelect: (tab: TabId) => void;
  aircraft: Aircraft[];
}

const NAV: { id: TabId; icon: string; label: string; emergency?: boolean }[] = [
  { id: 'monitoring', icon: '◉', label: 'Monitoring' },
  { id: 'visualization', icon: '◈', label: 'Airspace View' },
  { id: 'emergency', icon: '⚠', label: 'Emergency', emergency: true },
  { id: 'analytics', icon: '◎', label: 'Analytics' },
];

export default function Sidebar({ active, onSelect, aircraft }: SidebarProps) {
  const inFlight = aircraft.filter(a => a.status === 'in_flight').length;
  const emergencies = aircraft.filter(a => a.status === 'emergency').length;
  const charging = aircraft.filter(a => a.status === 'charging').length;

  return (
    <aside className="sidebar">
      <div className="sidebar-section-label">Navigation</div>

      {NAV.map(item => (
        <div
          key={item.id}
          className={`nav-item${active === item.id ? ' active' : ''}${item.emergency ? ' emergency-nav' : ''}`}
          onClick={() => onSelect(item.id)}
        >
          <span style={{ fontSize: 14 }}>{item.icon}</span>
          {item.label}
          {item.emergency && emergencies > 0 && (
            <span style={{
              marginLeft: 'auto', background: 'var(--red)', color: 'white',
              borderRadius: '10px', padding: '0 6px', fontSize: '10px', fontWeight: 700,
            }}>
              {emergencies}
            </span>
          )}
        </div>
      ))}

      <div className="sidebar-footer">
        <div className="sidebar-stat">
          <span>In Flight</span>
          <span style={{ color: 'var(--accent)' }}>{inFlight}</span>
        </div>
        <div className="sidebar-stat">
          <span>Charging</span>
          <span style={{ color: 'var(--green)' }}>{charging}</span>
        </div>
        <div className="sidebar-stat">
          <span>Emergency</span>
          <span style={{ color: 'var(--red)' }}>{emergencies}</span>
        </div>
        <div className="sidebar-stat" style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--border)' }}>
          <span>Total Fleet</span>
          <span>{aircraft.length}</span>
        </div>
      </div>
    </aside>
  );
}
