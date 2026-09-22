import { Button, EmptyState, LoadingState } from '@/components/ui';
import { useSites } from '@/features/estate';
import { EstateGrid, KpiStrip } from '@/features/estate';
import { useAlerts, AlertQueue } from '@/features/alerts';
import { EventTicker } from '@/features/simulation';

export function EstatePage() {
  const sitesQuery = useSites();
  const alertsQuery = useAlerts();

  return (
    <div>
      <header className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[22px] font-medium tracking-tight leading-tight">Estate</h1>
          <p className="mt-1 text-[12.5px] text-text2">
            Real-time health across 7 properties · 35 integrations · 248 monitored devices
          </p>
        </div>
        <div className="flex gap-1.5">
          <Button icon={
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.4} className="h-2.5 w-2.5">
              <path d="M2 8h12M8 2v12" />
            </svg>
          }>
            Add property
          </Button>
          <Button icon={
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.4} className="h-2.5 w-2.5">
              <path d="M8 2v8M5 7l3 3 3-3M2 12v2h12v-2" />
            </svg>
          }>
            Export
          </Button>
          <Button variant="prime">Acknowledge all</Button>
        </div>
      </header>

      <EventTicker />
      <KpiStrip />

      {alertsQuery.isPending ? (
        <LoadingState label="Loading alerts…" />
      ) : alertsQuery.isError ? (
        <EmptyState title="Could not load alerts" description={(alertsQuery.error as Error).message} />
      ) : alertsQuery.data && alertsQuery.data.length > 0 ? (
        <AlertQueue alerts={alertsQuery.data} />
      ) : (
        <EmptyState title="No active alerts" description="The estate is currently green." />
      )}

      <section className="mt-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-[11px] uppercase tracking-wider text-text3">Sort</span>
            <button type="button" className="filter-pill active">Worst first</button>
            <button type="button" className="filter-pill">Name</button>
            <button type="button" className="filter-pill">Brand</button>
            <button type="button" className="filter-pill">Region</button>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="chip chip-dim">7 sites</span>
            <span className="chip chip-red">1 critical</span>
            <span className="chip chip-amber">2 warn</span>
            <span className="chip chip-green">4 healthy</span>
          </div>
        </div>

        {sitesQuery.isPending ? (
          <LoadingState label="Loading sites…" />
        ) : sitesQuery.isError ? (
          <EmptyState title="Could not load estate" description={(sitesQuery.error as Error).message} />
        ) : sitesQuery.data ? (
          <EstateGrid sites={sitesQuery.data} />
        ) : null}
      </section>
    </div>
  );
}
