import { Outlet, useLocation, useMatches } from 'react-router-dom';
import { useMemo } from 'react';

import type { AppRouteHandle } from '@/app/routeHandles';
import { AppShell, Breadcrumbs, Topbar, type BreadcrumbItem } from '@/components/layout';
import { ROUTES } from '@/constants/routes';
import { FloatAlerts, SimulationProvider } from '@/features/simulation';

export function DashboardLayout() {
  const matches = useMatches();
  const location = useLocation();

  const breadcrumbs = useMemo<BreadcrumbItem[]>(() => {
    const last = matches[matches.length - 1];
    const handle = (last?.handle ?? {}) as AppRouteHandle;
    if (typeof handle.breadcrumbs === 'function') {
      return handle.breadcrumbs({ params: (last?.params ?? {}) as Record<string, string | undefined> });
    }
    if (Array.isArray(handle.breadcrumbs)) return handle.breadcrumbs;
    return [{ label: 'Estate', to: ROUTES.estate }];
  }, [matches]);

  return (
    <SimulationProvider>
      <AppShell>
        <Topbar breadcrumbs={<Breadcrumbs items={breadcrumbs} />} />
        <FloatAlerts />
        <main key={location.pathname} className="flex-1 px-5 pb-10 pt-4 page-fade-in">
          <Outlet />
        </main>
      </AppShell>
    </SimulationProvider>
  );
}
