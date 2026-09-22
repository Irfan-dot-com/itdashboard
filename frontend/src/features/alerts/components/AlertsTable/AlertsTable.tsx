import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';

import { SeverityPill } from '@/components/ui';
import { buildAlertPath } from '@/constants/routes';
import type { AlertSummary, Severity } from '@/models';

interface AlertsTableProps {
  alerts: AlertSummary[];
}

const SEVERITY_RANK: Record<Severity, number> = {
  p1: 0,
  p2: 1,
  p3: 2,
  info: 3,
};

function severityPillTone(sev: Severity): 'crit' | 'warn' | 'info' {
  if (sev === 'p1') return 'crit';
  if (sev === 'p2') return 'warn';
  return 'info';
}

function compareAlerts(a: AlertSummary, b: AlertSummary): number {
  const bySev = SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity];
  if (bySev !== 0) return bySev;
  return b.id.localeCompare(a.id);
}

export function AlertsTable({ alerts }: AlertsTableProps) {
  const navigate = useNavigate();
  const rows = useMemo(() => [...alerts].sort(compareAlerts), [alerts]);

  return (
    <div className="it-card">
      <div className="it-card-head">
        <div>
          <div className="it-card-title">Open alerts</div>
          <div className="it-card-sub">Click any alert to view detail with causal chain</div>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="it-table">
          <thead>
            <tr>
              <th scope="col">ID</th>
              <th scope="col">Severity</th>
              <th scope="col">Property</th>
              <th scope="col">Summary</th>
              <th scope="col">Opened</th>
              <th scope="col">Triaged by</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((alert) => (
              <tr
                key={alert.id}
                className="cursor-pointer"
                onClick={() => navigate(buildAlertPath(alert.id))}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    navigate(buildAlertPath(alert.id));
                  }
                }}
                tabIndex={0}
                role="link"
                aria-label={`Open alert ${alert.id}`}
              >
                <td className="mono">{alert.id}</td>
                <td>
                  <SeverityPill tone={severityPillTone(alert.severity)}>
                    {alert.severity.toUpperCase()}
                  </SeverityPill>
                </td>
                <td>{alert.site}</td>
                <td>{alert.summary}</td>
                <td className="mono">{alert.time}</td>
                <td>{alert.triagedBy}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
