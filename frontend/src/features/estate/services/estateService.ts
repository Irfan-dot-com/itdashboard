import { apiClient } from '@/lib/api/client';
import { endpoints } from '@/lib/api/endpoints';
import type { PropertySummary } from '@/models';

export const estateService = {
  list: () => apiClient.get<PropertySummary[]>(endpoints.sites()),
  detail: (siteId: string) => apiClient.get<PropertySummary>(endpoints.site(siteId)),
};
