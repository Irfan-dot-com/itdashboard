import type { BreadcrumbItem } from '@/components/layout';

/** Route handles read by DashboardLayout via `useMatches`. */
export interface AppRouteHandle {
  breadcrumbs?:
    | BreadcrumbItem[]
    | ((args: { params: Record<string, string | undefined> }) => BreadcrumbItem[]);
}
