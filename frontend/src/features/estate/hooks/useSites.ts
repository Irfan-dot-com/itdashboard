import { useQuery } from '@tanstack/react-query';

import { queryKeys } from '@/lib/query/queryKeys';

import { estateService } from '../services/estateService';

export function useSites() {
  return useQuery({
    queryKey: queryKeys.sites.list(),
    queryFn: estateService.list,
  });
}

export function useSite(siteId: string) {
  return useQuery({
    queryKey: queryKeys.sites.detail(siteId),
    queryFn: () => estateService.detail(siteId),
    enabled: Boolean(siteId),
  });
}
