import type { ReactNode } from 'react';

import { ROUTES } from './routes';

export interface NavItemDef {
  key: string;
  label: string;
  path: string;
  icon: ReactNode;
  badge?: { label: string; tone: 'red' | 'amber' | 'ok' | 'live' };
}

export interface NavGroupDef {
  label: string;
  items: NavItemDef[];
}

const iconProps = {
  viewBox: '0 0 16 16',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.4,
  className: 'h-3.5 w-3.5 flex-shrink-0',
} as const;

export const NAV_GROUPS: NavGroupDef[] = [
  {
    label: 'Operational',
    items: [
      {
        key: 'estate',
        label: 'Estate',
        path: ROUTES.estate,
        icon: (
          <svg {...iconProps}>
            <rect x="2" y="2" width="5" height="5" rx="1" />
            <rect x="9" y="2" width="5" height="5" rx="1" />
            <rect x="2" y="9" width="5" height="5" rx="1" />
            <rect x="9" y="9" width="5" height="5" rx="1" />
          </svg>
        ),
        badge: { label: '3', tone: 'red' },
      },
      {
        key: 'alerts',
        label: 'Alerts',
        path: ROUTES.alerts,
        icon: (
          <svg {...iconProps}>
            <path d="M3 13l5-10 5 10H3z" />
            <path d="M8 7v3M8 11.5v.5" />
          </svg>
        ),
        badge: { label: '7', tone: 'amber' },
      },
      {
        key: 'events',
        label: 'Live events',
        path: ROUTES.events,
        icon: (
          <svg {...iconProps}>
            <path d="M2 4h12M2 8h8M2 12h10" />
          </svg>
        ),
        badge: { label: 'live', tone: 'live' },
      },
      {
        key: 'oncall',
        label: 'On-call',
        path: ROUTES.oncall,
        icon: (
          <svg {...iconProps}>
            <circle cx="8" cy="6" r="3" />
            <path d="M2 14c.5-2.5 3-4 6-4s5.5 1.5 6 4" />
          </svg>
        ),
      },
    ],
  },
  {
    label: 'Service',
    items: [
      {
        key: 'wakeup',
        label: 'Wake-up calls',
        path: ROUTES.wakeup,
        icon: (
          <svg {...iconProps}>
            <circle cx="8" cy="8" r="5" />
            <path d="M8 5v3l2 2" strokeLinecap="round" />
          </svg>
        ),
        badge: { label: '3', tone: 'amber' },
      },
      {
        key: 'maintenance',
        label: 'Maintenance',
        path: ROUTES.maintenance,
        icon: (
          <svg {...iconProps}>
            <path d="M13 3l-2 2-1.5-1.5 2-2A3 3 0 003 5.5L1 10l2 2 4-2a3 3 0 104.5-4.5L13 3z" />
          </svg>
        ),
        badge: { label: '3', tone: 'amber' },
      },
      {
        key: 'queue',
        label: 'Event queue',
        path: ROUTES.queue,
        icon: (
          <svg {...iconProps}>
            <rect x="2" y="2" width="12" height="12" rx="1.5" />
            <path d="M5 8h6M5 5h6M5 11h4" strokeLinecap="round" />
          </svg>
        ),
        badge: { label: '6', tone: 'amber' },
      },
    ],
  },
  {
    label: 'Estate',
    items: [
      {
        key: 'devices',
        label: 'Device estate',
        path: ROUTES.devices,
        icon: (
          <svg {...iconProps}>
            <rect x="2" y="3" width="12" height="7" rx="1" />
            <path d="M5 13h6M8 10v3" />
          </svg>
        ),
      },
      {
        key: 'integrations',
        label: 'Integrations',
        path: ROUTES.integrations,
        icon: (
          <svg {...iconProps}>
            <circle cx="3" cy="8" r="1.6" />
            <circle cx="13" cy="4" r="1.6" />
            <circle cx="13" cy="12" r="1.6" />
            <path d="M4.5 8H8M8 8V4.5h3M8 8v3.5h3" />
          </svg>
        ),
        badge: { label: '1', tone: 'amber' },
      },
      {
        key: 'agents',
        label: 'Agent activity',
        path: ROUTES.agents,
        icon: (
          <svg {...iconProps}>
            <circle cx="8" cy="8" r="5" />
            <circle cx="8" cy="8" r="2" fill="currentColor" />
          </svg>
        ),
      },
    ],
  },
  {
    label: 'Strategic',
    items: [
      {
        key: 'exec',
        label: 'Executive',
        path: ROUTES.executive,
        icon: (
          <svg {...iconProps}>
            <path d="M2 13l4-4 3 3 5-7" />
            <path d="M11 5h3v3" />
          </svg>
        ),
      },
      {
        key: 'risk',
        label: 'Risk & debt',
        path: ROUTES.risk,
        icon: (
          <svg {...iconProps}>
            <path d="M8 1l6 3v4c0 4-3 6-6 7-3-1-6-3-6-7V4l6-3z" />
          </svg>
        ),
      },
      {
        key: 'kpi',
        label: 'KPIs & SLAs',
        path: ROUTES.kpi,
        icon: (
          <svg {...iconProps}>
            <rect x="2" y="9" width="3" height="5" />
            <rect x="6.5" y="5" width="3" height="9" />
            <rect x="11" y="2" width="3" height="12" />
          </svg>
        ),
      },
      {
        key: 'rules',
        label: 'Alert rules',
        path: ROUTES.rules,
        icon: (
          <svg {...iconProps}>
            <path d="M8 2a5 5 0 015 5v2l1 2H2l1-2V7a5 5 0 015-5z" />
            <path d="M6.5 13a1.5 1.5 0 003 0" />
          </svg>
        ),
      },
    ],
  },
];
