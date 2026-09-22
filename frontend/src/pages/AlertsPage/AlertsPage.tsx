import { Button, EmptyState, LoadingState } from '@/components/ui';
import { AlertsTable, useAlerts } from '@/features/alerts';

export function AlertsPage() {
  const { data, isPending, isError, error } = useAlerts();
  const count = data?.length ?? 0;

  return (
    <div>
      <header className="page-head">
        <div>
          <h1 className="page-h1">Alerts</h1>
          <p className="page-sub">
            Full alert queue · {count} active · severity-sorted
          </p>
        </div>
        <div className="flex gap-1.5">
          <Button>Filters</Button>
          <Button variant="prime">Acknowledge all</Button>
        </div>
      </header>

      {isPending ? (
        <LoadingState label="Loading alerts…" />
      ) : isError ? (
        <EmptyState title="Could not load alerts" description={(error as Error).message} />
      ) : data && data.length > 0 ? (
        <AlertsTable alerts={data} />
      ) : (
        <EmptyState title="No active alerts" description="Nothing requires attention right now." />
      )}
    </div>
  );
}
