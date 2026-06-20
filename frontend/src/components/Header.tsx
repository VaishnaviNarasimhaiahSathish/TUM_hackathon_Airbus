import { useEffect, useState } from 'react';
import type { Alert } from '../types';

export default function Header({
  systemStatus,
  alerts,
  connected,
}: {
  systemStatus: 'normal' | 'warning' | 'emergency';
  alerts: Alert[];
  connected: boolean;
}) {
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const criticalCount = alerts.filter(a => a.level === 'critical').length;
  const statusLabel = systemStatus === 'emergency' ? 'EMERGENCY' : systemStatus === 'warning' ? 'WARNING' : 'NORMAL OPS';

  return (
    <header className="header">
      <div className="header-brand">
        <div className="header-logo">A</div>
        <div>
          <div className="header-title">Airbus Control Center</div>
          <div className="header-subtitle">Urban Air Mobility · Munich</div>
        </div>
      </div>

      <div className="header-center">
        <div className={`system-status ${systemStatus}`}>
          <span className="pulse-dot" />
          {statusLabel}
        </div>
      </div>

      <div className="header-right">
        <div className="alert-badge">
          <span style={{ marginRight: 6 }}>{connected ? 'LIVE' : 'SAMPLE'}</span>
          ⚠ {criticalCount} CRITICAL
        </div>
        <div className="header-clock">
          {time.toLocaleTimeString('en-GB')}
        </div>
      </div>
    </header>
  );
}
