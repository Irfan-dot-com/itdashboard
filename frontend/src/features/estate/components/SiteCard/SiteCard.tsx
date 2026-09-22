import { useNavigate } from 'react-router-dom';

import { SparkLineChart } from '@/components/charts';
import { StatusDot } from '@/components/ui';
import { buildPropertyPath } from '@/constants/routes';
import { cn } from '@/lib/utils/cn';
import type { PropertySummary } from '@/models';

import { gradeColor, scoreColorClass } from '../../utils/gradeColors';

interface SiteCardProps {
  site: PropertySummary;
}

export function SiteCard({ site }: SiteCardProps) {
  const navigate = useNavigate();
  const color = gradeColor(site.grade);

  return (
    <button
      type="button"
      onClick={() => navigate(buildPropertyPath(site.id))}
      className={cn(
        'group relative overflow-hidden rounded-token-lg border border-border bg-surface px-4 pb-3 pt-3.5 text-left transition-all hover:-translate-y-px hover:border-border3 cursor-pointer',
        site.grade === 'crit' && 'border-red-dim before:absolute before:left-0 before:top-0 before:bottom-0 before:w-0.5 before:bg-red',
        site.grade === 'warn' && 'border-amber-dim before:absolute before:left-0 before:top-0 before:bottom-0 before:w-0.5 before:bg-amber',
      )}
    >
      <div className="mb-2.5 flex items-start justify-between">
        <div>
          <div className="text-sm font-medium leading-tight">{site.name}</div>
          <div className="mt-0.5 font-mono text-[10.5px] text-text3">{site.meta}</div>
        </div>
        <div className={cn('font-mono text-lg font-medium leading-none tracking-tight', scoreColorClass(site.score))}>
          {site.score}
        </div>
      </div>

      <div className="relative my-2 h-8">
        <SparkLineChart data={site.spark} color={color} suggestedMin={30} suggestedMax={100} ariaLabel={`${site.name} health trend`} />
      </div>

      <div className="flex items-center gap-1.5 border-t border-border pt-2 text-[11px] text-text2">
        <div className="flex gap-2 font-mono text-[11px]">
          <span className="flex items-center gap-0.5 text-red">P1 {site.alerts.p1}</span>
          <span className="flex items-center gap-0.5 text-amber">P2 {site.alerts.p2}</span>
          <span className="flex items-center gap-0.5 text-text3">P3 {site.alerts.p3}</span>
        </div>
      </div>

      <div className="mt-2 flex items-center gap-1.5 text-[11px] leading-tight text-text2">
        <StatusDot
          tone={site.grade === 'crit' ? 'red' : site.grade === 'warn' ? 'amber' : 'green'}
          pulsing={site.grade !== 'ok'}
        />
        <div className="flex-1">
          <span className="font-medium text-text">{site.worst}</span>
          {site.worstSig ? <span> · {site.worstSig}</span> : null}
        </div>
      </div>
    </button>
  );
}
