import { SparkLineChart } from '@/components/charts';
import { cn } from '@/lib/utils/cn';
import { EXEC_KPIS } from '@/mocks/fixtures/metrics';

const toneClass: Record<string, string> = {
  ok: 'text-green',
  warn: 'text-amber',
  crit: 'text-red',
  neutral: '',
};

export function ExecKpiGrid() {
  return (
    <div className="grid grid-cols-4 gap-3 max-md:grid-cols-2 max-sm:grid-cols-1">
      {EXEC_KPIS.map((kpi) => (
        <div key={kpi.id} className="rounded-token-lg border border-border bg-surface p-4">
          <div className="mb-2.5 flex items-start justify-between gap-2.5">
            <div className="text-[11px] font-medium uppercase leading-tight tracking-wider text-text3">
              {kpi.label}
            </div>
          </div>
          <div className={cn('mb-1.5 font-mono text-3xl font-medium leading-none tracking-tight', toneClass[kpi.tone ?? 'neutral'])}>
            {kpi.value}
          </div>
          <div className="text-[11px] text-text2">{kpi.delta}</div>
          <div className="relative mt-2.5 h-20">
            <SparkLineChart data={kpi.spark} color={kpi.color} ariaLabel={`${kpi.label} trend`} />
          </div>
        </div>
      ))}
    </div>
  );
}
