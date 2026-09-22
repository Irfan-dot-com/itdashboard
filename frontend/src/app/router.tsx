import { createBrowserRouter } from 'react-router-dom';

import { ROUTES } from '@/constants/routes';
import {
  AlertDetailPage,
  AlertsPage,
  EstatePage,
  ExecutivePage,
  PropertyDetailPage,
  StubPage,
} from '@/pages';

import { NotFoundPage } from './error/NotFoundPage';
import { DashboardLayout } from './layouts/DashboardLayout';
import type { AppRouteHandle } from './routeHandles';

const estateTrail = [{ label: 'Estate', to: ROUTES.estate }] as const;

export const appRouter = createBrowserRouter(
  [
  {
    path: '/',
    element: <DashboardLayout />,
    children: [
      {
        index: true,
        element: <EstatePage />,
        handle: { breadcrumbs: [{ label: 'Estate' }] } satisfies AppRouteHandle,
      },
      {
        path: 'alerts',
        element: <AlertsPage />,
        handle: { breadcrumbs: [...estateTrail, { label: 'Alerts' }] } satisfies AppRouteHandle,
      },
      {
        path: 'alerts/:alertId',
        element: <AlertDetailPage />,
        handle: {
          breadcrumbs: ({ params }: { params: Record<string, string | undefined> }) => [
            ...estateTrail,
            { label: 'Alerts', to: ROUTES.alerts },
            { label: params.alertId ? `Alert · ${params.alertId}` : 'Alert' },
          ],
        } satisfies AppRouteHandle,
      },
      {
        path: 'properties/:propertyId',
        element: <PropertyDetailPage />,
        handle: {
          breadcrumbs: ({ params }: { params: Record<string, string | undefined> }) => [
            ...estateTrail,
            {
              label: params.propertyId ? `Property · ${params.propertyId}` : 'Property',
            },
          ],
        } satisfies AppRouteHandle,
      },
      {
        path: 'executive',
        element: <ExecutivePage />,
        handle: { breadcrumbs: [...estateTrail, { label: 'Executive view' }] } satisfies AppRouteHandle,
      },
      {
        path: 'events',
        element: <StubPage title="Live events" description="Streaming event spine across the estate." />,
        handle: { breadcrumbs: [...estateTrail, { label: 'Live events' }] } satisfies AppRouteHandle,
      },
      {
        path: 'oncall',
        element: <StubPage title="On-call" description="Rotations, escalations, and active responders." />,
        handle: { breadcrumbs: [...estateTrail, { label: 'On-call' }] } satisfies AppRouteHandle,
      },
      {
        path: 'wakeup',
        element: (
          <StubPage title="Wake-up calls" description="Wake-up SLA and recent failures per property." />
        ),
        handle: { breadcrumbs: [...estateTrail, { label: 'Wake-up calls' }] } satisfies AppRouteHandle,
      },
      {
        path: 'maintenance',
        element: <StubPage title="Maintenance" description="Scheduled and reactive maintenance tickets." />,
        handle: { breadcrumbs: [...estateTrail, { label: 'Maintenance' }] } satisfies AppRouteHandle,
      },
      {
        path: 'queue',
        element: (
          <StubPage title="Event queue" description="Triage queue for incoming events awaiting routing." />
        ),
        handle: { breadcrumbs: [...estateTrail, { label: 'Event queue' }] } satisfies AppRouteHandle,
      },
      {
        path: 'devices',
        element: (
          <StubPage title="Device estate" description="All monitored devices by class, vendor, and site." />
        ),
        handle: { breadcrumbs: [...estateTrail, { label: 'Device estate' }] } satisfies AppRouteHandle,
      },
      {
        path: 'integrations',
        element: (
          <StubPage title="Integrations" description="External integrations, heartbeats, and dormancy." />
        ),
        handle: { breadcrumbs: [...estateTrail, { label: 'Integrations' }] } satisfies AppRouteHandle,
      },
      {
        path: 'agents',
        element: (
          <StubPage title="Agent activity" description="Tamper-evident audit trail per agent decision." />
        ),
        handle: { breadcrumbs: [...estateTrail, { label: 'Agent activity' }] } satisfies AppRouteHandle,
      },
      {
        path: 'risk',
        element: (
          <StubPage title="Risk & debt" description="Technical debt index, EoL hardware, and refresh roadmap." />
        ),
        handle: { breadcrumbs: [...estateTrail, { label: 'Risk & debt' }] } satisfies AppRouteHandle,
      },
      {
        path: 'kpi',
        element: <StubPage title="KPIs & SLAs" description="Service KPIs, SLAs, and breach reporting." />,
        handle: { breadcrumbs: [...estateTrail, { label: 'KPIs & SLAs' }] } satisfies AppRouteHandle,
      },
      {
        path: 'rules',
        element: <StubPage title="Alert rules" description="Rule editor for alerting and severity policies." />,
        handle: { breadcrumbs: [...estateTrail, { label: 'Alert rules' }] } satisfies AppRouteHandle,
      },
      {
        path: '*',
        element: <NotFoundPage />,
      },
    ],
  },
],
  {
    future: {
      v7_relativeSplatPath: true,
    },
  },
);
