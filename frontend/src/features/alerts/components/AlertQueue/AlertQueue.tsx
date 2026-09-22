import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Chip } from '@/components/ui';
import { buildAlertPath } from '@/constants/routes';
import { cn } from '@/lib/utils/cn';
import type { AlertSummary, Severity } from '@/models';

import { severityBarClass } from '../../utils/severity';

interface AlertQueueProps {
  alerts: AlertSummary[];
}

type Filter = 'all' | 'p1' | 'p2' | 'unack';

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'p1', label: 'P1' },
  { key: 'p2', label: 'P2' },
  { key: 'unack', label: 'Unack' },
];

export function AlertQueue({ alerts }: AlertQueueProps) {
  const [filter, setFilter] = useState<Filter>('all');
  const navigate = useNavigate();

  const filtered = useMemo(() => {
    return alerts.filter((alert) => {
      if (filter === 'all') return true;
      if (filter === 'p1' || filter === 'p2') return alert.severity === (filter as Severity);
      if (filter === 'unack') return !alert.agent;
      return true;
    });
  }, [alerts, filter]);

  return (
    <section
      aria-label="Active alerts"
      className="mb-3.5 overflow-hidden rounded-token-lg border border-border bg-surface"
    >
      <header className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <div className="flex items-center gap-2 text-[12.5px] font-medium">
          Active alerts
          <span className="font-mono text-[11px] font-normal text-text3">
            {alerts.length} open · {alerts.filter((a) => a.agent).length} acknowledged
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {FILTERS.map((entry) => (
            <button
              type="button"
              key={entry.key}
              onClick={() => setFilter(entry.key)}
              className={cn('filter-pill', filter === entry.key && 'active')}
            >
              {entry.label}
            </button>
          ))}
        </div>
      </header>

      <div className="flex flex-col">
        {filtered.map((alert) => (
          <button
            type="button"
            key={alert.id}
            onClick={() => navigate(buildAlertPath(alert.id))}
            className="grid grid-cols-[6px_80px_90px_1fr_100px_90px_28px] items-center gap-3.5 border-b border-border px-4 py-2.5 text-left transition-colors last:border-b-0 hover:bg-surface2"
          >
            <span className={cn('h-7 w-[3px] rounded-[1.5px]', severityBarClass(alert.severity))} />
            <span className="font-mono text-[11px] text-text3">{alert.time}</span>
            <span className="text-[11.5px] font-medium">{alert.site}</span>
            <span className="flex min-w-0 flex-col gap-0.5">
              <span className="text-xs font-medium leading-snug">{alert.summary}</span>
              <span className="text-[11px] leading-snug text-text2">{alert.detail}</span>
            </span>
            <span className="text-right text-[11px] text-text3">
              {alert.impact ? (
                <>
                  <span className="block font-medium text-text">{alert.impact}</span>
                  <span>{alert.impactLabel}</span>
                </>
              ) : null}
            </span>
            <span className="flex justify-end">
              {alert.agent ? <span className="agent-tag">triaged</span> : <Chip tone="dim">manual</Chip>}
            </span>
            <span className="text-right text-text3">›</span>
          </button>
        ))}
        {filtered.length === 0 ? (
          <div className="px-4 py-6 text-center text-xs text-text3">No alerts match this filter.</div>
        ) : null}
      </div>
    </section>
  );
}
