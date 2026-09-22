import { useParams, useNavigate } from 'react-router-dom';

import { SparkLineChart } from '@/components/charts';
import { Button, EmptyState, LoadingState } from '@/components/ui';
import { ROUTES } from '@/constants/routes';
import { useSite } from '@/features/estate';
import { gradeColor } from '@/features/estate';

export function PropertyDetailPage() {
  const params = useParams<{ propertyId: string }>();
  const navigate = useNavigate();
  const { data: site, isPending, isError, error } = useSite(params.propertyId ?? '');

  if (isPending) return <LoadingState label="Loading property…" />;
  if (isError) return <EmptyState title="Could not load property" description={(error as Error).message} />;
  if (!site) return <EmptyState title="Property not found" />;

  const initials = site.name.replace(/[^A-Z]/g, '').slice(0, 2) || site.name.slice(0, 2).toUpperCase();

  return (
    <div>
      <div className="mb-3.5">
        <Button
          variant="ghost"
          onClick={() => navigate(ROUTES.estate)}
          icon={
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.4} className="h-2.5 w-2.5">
              <path d="M10 3L5 8l5 5" />
            </svg>
          }
        >
          Back to estate
        </Button>
      </div>

      <header className="mb-3.5 flex flex-wrap items-end justify-between gap-3.5">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-[9px] border border-border2 bg-surface2 font-mono text-lg font-medium">
            {initials}
          </div>
          <div>
            <h1 className="text-[22px] font-medium leading-tight tracking-tight">{site.name}</h1>
            <div className="mt-1 font-mono text-xs text-text3">{site.meta}</div>
          </div>
        </div>
        <div className="flex flex-wrap gap-4 text-[11.5px]">
          <Stat label="Health score" value={site.score.toString()} />
          <Stat label="Open P1" value={site.alerts.p1.toString()} />
          <Stat label="Open P2" value={site.alerts.p2.toString()} />
        </div>
      </header>

      <div className="rounded-token-lg border border-border bg-surface p-4">
        <div className="mb-1.5 text-xs font-medium">Health trend · last 12 hours</div>
        <div className="text-[11px] text-text3">{site.worst}{site.worstSig ? ` · ${site.worstSig}` : ''}</div>
        <div className="relative mt-4 h-32">
          <SparkLineChart data={site.spark} color={gradeColor(site.grade)} ariaLabel={`${site.name} health trend`} />
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10.5px] uppercase tracking-wide text-text3">{label}</div>
      <div className="font-mono text-[14px] font-medium">{value}</div>
    </div>
  );
}
