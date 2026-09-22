import { describe, expect, it } from 'vitest';

import { renderWithProviders, screen } from '@/test/test-utils';
import type { PropertySummary } from '@/models';

import { SiteCard } from './SiteCard';

const SITE: PropertySummary = {
  id: 'cottons',
  name: 'Cottons Hotel',
  meta: 'Knutsford · 89 keys',
  score: 71,
  grade: 'warn',
  alerts: { p1: 1, p2: 1, p3: 0 },
  worst: 'DECT registrations dropped',
  worstSig: '8 handsets unreg',
  spark: [88, 80, 72, 71],
};

describe('SiteCard', () => {
  it('renders site name and score', () => {
    renderWithProviders(<SiteCard site={SITE} />);
    expect(screen.getByText('Cottons Hotel')).toBeInTheDocument();
    expect(screen.getByText('71')).toBeInTheDocument();
  });

  it('shows worst signal message', () => {
    renderWithProviders(<SiteCard site={SITE} />);
    expect(screen.getByText(/DECT registrations dropped/)).toBeInTheDocument();
  });
});
