import { describe, expect, it } from 'vitest';

import { formatCurrency, formatNumber, formatPercent } from './format';

describe('format utilities', () => {
  it('formats numbers without fractions by default', () => {
    expect(formatNumber(1234)).toBe('1,234');
  });

  it('formats percent with one fraction digit by default', () => {
    expect(formatPercent(93.625)).toBe('93.6%');
  });

  it('formats currency in GBP by default', () => {
    expect(formatCurrency(14200)).toMatch(/£14,200/);
  });
});
