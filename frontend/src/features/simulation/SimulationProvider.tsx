import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

import { env } from '@/lib/env/env';
import { formatClock } from '@/lib/utils/date';
import { SIM_EVENTS } from '@/mocks/fixtures/events';
import type { TickerEvent } from '@/models';

import { SimulationContext } from './simulation-context';
import type { FloatAlert } from './types';

const TICKER_LIMIT = 8;
const FLOAT_TIMEOUT_MS = 14_000;

export function SimulationProvider({ children }: { children: ReactNode }) {
  const [running, setRunning] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [ticker, setTicker] = useState<TickerEvent[]>([]);
  const [floats, setFloats] = useState<FloatAlert[]>([]);

  const tickerIntervalRef = useRef<number | null>(null);
  const elapsedIntervalRef = useRef<number | null>(null);
  const timeoutsRef = useRef<number[]>([]);
  const startedAtRef = useRef<number>(0);

  const clearScheduled = useCallback(() => {
    if (tickerIntervalRef.current) window.clearInterval(tickerIntervalRef.current);
    if (elapsedIntervalRef.current) window.clearInterval(elapsedIntervalRef.current);
    timeoutsRef.current.forEach((handle) => window.clearTimeout(handle));
    tickerIntervalRef.current = null;
    elapsedIntervalRef.current = null;
    timeoutsRef.current = [];
  }, []);

  const pushTickerEvent = useCallback((event: TickerEvent) => {
    const entry: TickerEvent = { ...event, id: `${event.id}-${Date.now()}`, timestamp: formatClock() };
    setTicker((prev) => [entry, ...prev].slice(0, TICKER_LIMIT));
  }, []);

  const showFloat = useCallback((float: FloatAlert) => {
    const id = `${float.id}-${Date.now()}`;
    setFloats((prev) => [...prev, { ...float, id }]);
    const handle = window.setTimeout(() => {
      setFloats((prev) => prev.filter((entry) => entry.id !== id));
    }, FLOAT_TIMEOUT_MS);
    timeoutsRef.current.push(handle);
  }, []);

  const start = useCallback(() => {
    if (running || !env.enableSimulation) return;
    setRunning(true);
    startedAtRef.current = Date.now();
    setElapsedSeconds(0);

    const continuous = SIM_EVENTS.flatMap((trigger) =>
      trigger.kind === 'continuous' ? [trigger.event] : [],
    );

    tickerIntervalRef.current = window.setInterval(() => {
      const random = continuous[Math.floor(Math.random() * continuous.length)];
      if (random) pushTickerEvent(random);
    }, 3500);

    elapsedIntervalRef.current = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAtRef.current) / 1000));
    }, 1000);

    SIM_EVENTS.forEach((trigger) => {
      if (trigger.kind !== 'timed') return;
      const handle = window.setTimeout(() => {
        pushTickerEvent(trigger.event);
        if (trigger.float) {
          showFloat({
            id: trigger.event.id,
            type: trigger.float.type,
            title: trigger.float.title,
            body: trigger.float.body,
            meta: trigger.float.meta,
          });
        }
      }, trigger.offsetMs);
      timeoutsRef.current.push(handle);
    });
  }, [running, pushTickerEvent, showFloat]);

  const stop = useCallback(() => {
    setRunning(false);
    setElapsedSeconds(0);
    setFloats([]);
    clearScheduled();
  }, [clearScheduled]);

  const toggle = useCallback(() => (running ? stop() : start()), [running, start, stop]);

  const dismissFloat = useCallback((id: string) => {
    setFloats((prev) => prev.filter((entry) => entry.id !== id));
  }, []);

  useEffect(() => () => clearScheduled(), [clearScheduled]);

  const value = useMemo(
    () => ({ running, elapsedSeconds, ticker, floats, start, stop, toggle, dismissFloat }),
    [running, elapsedSeconds, ticker, floats, start, stop, toggle, dismissFloat],
  );

  return <SimulationContext.Provider value={value}>{children}</SimulationContext.Provider>;
}
