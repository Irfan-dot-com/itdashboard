import type { TickerSeverity } from './common';

export interface TickerEvent {
  id: string;
  severity: TickerSeverity;
  label: string;
  property: string;
  message: string;
  meta?: string;
  timestamp?: string;
}

export type SimulatedEventTrigger =
  | { kind: 'continuous'; event: TickerEvent }
  | {
      kind: 'timed';
      offsetMs: number;
      event: TickerEvent;
      float?: {
        type: TickerSeverity;
        title: string;
        body: string;
        meta?: string;
      };
    };
