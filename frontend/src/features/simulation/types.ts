import type { TickerEvent, TickerSeverity } from '@/models';

export interface FloatAlert {
  id: string;
  type: TickerSeverity;
  title: string;
  body: string;
  meta?: string;
}

export interface SimulationState {
  running: boolean;
  elapsedSeconds: number;
  ticker: TickerEvent[];
  floats: FloatAlert[];
}

export interface SimulationApi extends SimulationState {
  start: () => void;
  stop: () => void;
  toggle: () => void;
  dismissFloat: (id: string) => void;
}
