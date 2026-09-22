export const queryKeys = {
  sites: {
    all: ['sites'] as const,
    list: () => [...queryKeys.sites.all, 'list'] as const,
    detail: (siteId: string) => [...queryKeys.sites.all, 'detail', siteId] as const,
  },
  alerts: {
    all: ['alerts'] as const,
    list: () => [...queryKeys.alerts.all, 'list'] as const,
    detail: (alertId: string) => [...queryKeys.alerts.all, 'detail', alertId] as const,
  },
  metrics: {
    all: ['metrics'] as const,
    estate: () => [...queryKeys.metrics.all, 'estate'] as const,
  },
} as const;
