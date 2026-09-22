import { useQuery } from '@tanstack/react-query';

import { queryKeys } from '@/lib/query/queryKeys';

import { alertsService } from '../services/alertsService';

export function useAlerts() {
  return useQuery({
    queryKey: queryKeys.alerts.list(),
    queryFn: alertsService.list,
  });
}

export function useAlertDetail(alertId: string) {
  return useQuery({
    queryKey: queryKeys.alerts.detail(alertId),
    queryFn: () => alertsService.detail(alertId),
    enabled: Boolean(alertId),
  });
}
