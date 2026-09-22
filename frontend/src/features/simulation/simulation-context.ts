import { createContext } from 'react';

import type { SimulationApi } from './types';

export const SimulationContext = createContext<SimulationApi | null>(null);
