import { apiClient } from '@/lib/api/client';
import { endpoints } from '@/lib/api/endpoints';
import type { AlertDetail, AlertSummary } from '@/models';

export const alertsService = {
  list: () => apiClient.get<AlertSummary[]>(endpoints.alerts()),
  detail: (alertId: string) => apiClient.get<AlertDetail>(endpoints.alert(alertId)),
};
