import { ESTATE_KPIS } from '@/mocks/fixtures/metrics';
import { cn } from '@/lib/utils/cn';

const toneClass: Record<string, string> = {
  ok: 'text-green',
  warn: 'text-amber',
  crit: 'text-red',
  neutral: '',
};

export function KpiStrip() {
  return (
    <div
      className="mb-4 grid grid-cols-6 gap-px overflow-hidden rounded-token-lg border border-border bg-border max-md:grid-cols-3 max-sm:grid-cols-2"
      role="list"
      aria-label="Estate key performance indicators"
    >
      {ESTATE_KPIS.map((kpi) => (
        <div key={kpi.id} role="listitem" className="flex flex-col gap-1 bg-surface px-4 py-3.5">
          <div className="text-[10.5px] font-medium uppercase tracking-wider text-text3">{kpi.label}</div>
          <div
            className={cn(
              'font-mono text-2xl font-medium leading-none tracking-tight',
              toneClass[kpi.tone ?? 'neutral'],
            )}
          >
            {kpi.value}
          </div>
          {kpi.trend ? <div className="text-[10.5px] text-text3">{kpi.trend}</div> : null}
        </div>
      ))}
    </div>
  );
}
