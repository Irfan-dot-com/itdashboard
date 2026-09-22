export const endpoints = {
  sites: () => '/v1/sites',
  site: (siteId: string) => `/v1/sites/${siteId}`,
  alerts: () => '/v1/alerts',
  alert: (alertId: string) => `/v1/alerts/${alertId}`,
  metrics: () => '/v1/metrics/estate',
  events: () => '/v1/events',
} as const;
