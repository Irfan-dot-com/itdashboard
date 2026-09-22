import { useParams, useNavigate } from 'react-router-dom';

import { Button, EmptyState, LoadingState } from '@/components/ui';
import {
  ActionCard,
  AgentReasoning,
  AlertHero,
  AlertTimeline,
  CausalChain,
  OnCallCard,
  useAlertDetail,
} from '@/features/alerts';
import { ROUTES } from '@/constants/routes';

export function AlertDetailPage() {
  const params = useParams<{ alertId: string }>();
  const navigate = useNavigate();
  const alertId = params.alertId ?? '';
  const { data: alert, isPending, isError, error } = useAlertDetail(alertId);

  if (isPending) return <LoadingState label="Loading alert…" />;
  if (isError) return <EmptyState title="Could not load alert" description={(error as Error).message} />;
  if (!alert) return <EmptyState title="Alert not found" />;

  return (
    <div>
      <div className="mb-3.5 flex items-center justify-between">
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
        <div className="flex gap-1.5">
          <Button>Snooze</Button>
          <Button>Reassign</Button>
          <Button variant="danger">Page on-call</Button>
        </div>
      </div>

      <AlertHero alert={alert} />

      <div className="mb-4 grid grid-cols-[1fr_360px] gap-3.5 max-lg:grid-cols-1">
        <div className="flex min-w-0 flex-col gap-3.5">
          <CausalChain entries={alert.chain} />
          <AgentReasoning reasoning={alert.reasoning} />
          <AlertTimeline runbook={alert.runbook} />
        </div>
        <div>
          <ActionCard />
          <OnCallCard />
        </div>
      </div>
    </div>
  );
}
