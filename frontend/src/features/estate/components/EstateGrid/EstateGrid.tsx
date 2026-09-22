import type { PropertySummary } from '@/models';

import { SiteCard } from '../SiteCard';

interface EstateGridProps {
  sites: PropertySummary[];
}

export function EstateGrid({ sites }: EstateGridProps) {
  return (
    <div className="grid gap-2.5 [grid-template-columns:repeat(auto-fill,minmax(280px,1fr))]">
      {sites.map((site) => (
        <SiteCard key={site.id} site={site} />
      ))}
    </div>
  );
}
