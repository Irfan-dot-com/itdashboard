import { useContext } from 'react';

import { SimulationContext } from './simulation-context';
import type { SimulationApi } from './types';

export function useSimulation(): SimulationApi {
  const ctx = useContext(SimulationContext);
  if (!ctx) {
    throw new Error('useSimulation must be used inside SimulationProvider');
  }
  return ctx;
}
