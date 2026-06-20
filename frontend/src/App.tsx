import { useState } from 'react';
import type { TabId } from './types';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import MonitoringPage from './components/MonitoringPage';
import VisualizationPage from './components/VisualizationPage';
import EmergencyPage from './components/EmergencyPage';
import AnalyticsPage from './components/AnalyticsPage';
import { useDashboardSnapshot } from './data/dashboardData';

export default function App() {
  const [tab, setTab] = useState<TabId>('monitoring');
  const { dashboard, connected } = useDashboardSnapshot();

  // system has 1 emergency aircraft → "warning" level
  const systemStatus: 'normal' | 'warning' | 'emergency' = dashboard.metrics.emergency_count > 0
    ? 'emergency'
    : dashboard.alerts.some((alert) => alert.level === 'warning' || alert.level === 'critical')
      ? 'warning'
      : 'normal';

  return (
    <div className="app-shell">
      <Header systemStatus={systemStatus} alerts={dashboard.alerts} connected={connected} />
      <div className="app-body">
        <Sidebar active={tab} onSelect={setTab} aircraft={dashboard.agents} />
        {tab === 'visualization' ? (
          <VisualizationPage
            nodes={dashboard.nodes}
            edges={dashboard.edges}
            aircraft={dashboard.agents}
            simulation={dashboard.simulation}
          />
        ) : (
          <div className="main-content">
            {tab === 'monitoring' && (
              <MonitoringPage
                nodes={dashboard.nodes}
                aircraft={dashboard.agents}
                alerts={dashboard.alerts}
                simulation={dashboard.simulation}
              />
            )}
            {tab === 'emergency' && (
              <EmergencyPage aircraft={dashboard.agents} alerts={dashboard.alerts} />
            )}
            {tab === 'analytics' && (
              <AnalyticsPage
                nodes={dashboard.nodes}
                aircraft={dashboard.agents}
                weatherZones={dashboard.weather_zones}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
