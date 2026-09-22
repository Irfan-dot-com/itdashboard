export const ROUTES = {
  estate: '/',
  alerts: '/alerts',
  alertDetail: '/alerts/:alertId',
  propertyDetail: '/properties/:propertyId',
  events: '/events',
  oncall: '/oncall',
  wakeup: '/wakeup',
  maintenance: '/maintenance',
  queue: '/queue',
  devices: '/devices',
  integrations: '/integrations',
  agents: '/agents',
  executive: '/executive',
  risk: '/risk',
  kpi: '/kpi',
  rules: '/rules',
} as const;

export type RouteKey = keyof typeof ROUTES;

export const buildAlertPath = (alertId: string): string => `/alerts/${alertId}`;
export const buildPropertyPath = (propertyId: string): string => `/properties/${propertyId}`;
