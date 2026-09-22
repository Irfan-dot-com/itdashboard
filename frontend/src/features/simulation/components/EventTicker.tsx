import { cn } from '@/lib/utils/cn';
import type { TickerSeverity } from '@/models';

import { useSimulation } from '../useSimulation';

const severityClass: Record<TickerSeverity, string> = {
  info: 'bg-blue-bg text-blue',
  ok: 'bg-green-bg text-green',
  warn: 'bg-amber-bg text-amber',
  crit: 'bg-red-bg text-red',
  agent: 'bg-teal-bg text-teal',
};

export function EventTicker() {
  const { ticker, running } = useSimulation();

  return (
    <div className="mb-4 overflow-hidden rounded-token-lg border border-border bg-surface">
      <div className="flex items-center gap-2 border-b border-border bg-surface2 px-3.5 py-2 text-[10px] font-semibold uppercase tracking-widest text-text3">
        <span className={cn('h-1.5 w-1.5 rounded-full bg-green', running && 'animate-pulse')} />
        <span>Live event stream</span>
        <span className="ml-auto font-mono text-[10px] font-medium tracking-normal normal-case text-text2">
          {ticker.length} events
        </span>
      </div>
      <div className="relative max-h-[200px] min-h-[48px] overflow-hidden">
        {ticker.length === 0 ? (
          <div className="px-3.5 py-2 text-[11.5px] text-text3 font-mono">
            Toggle <strong>Static → Live</strong> in the topbar to stream events.
          </div>
        ) : (
          ticker.map((event) => (
            <div
              key={event.id}
              className="grid grid-cols-[60px_80px_100px_1fr_80px] items-center gap-3.5 border-b border-border px-3.5 py-1.5 font-mono text-[11.5px] animate-ticker-slide"
            >
              <span className="text-[10px] text-text3">{event.timestamp ?? '—'}</span>
              <span>
                <span
                  className={cn(
                    'rounded-[8px] px-1.5 py-[1px] text-center font-sans text-[9.5px] font-bold uppercase tracking-wide',
                    severityClass[event.severity],
                  )}
                >
                  {event.label}
                </span>
              </span>
              <span className="font-sans font-medium text-text2">{event.property}</span>
              <span
                className="truncate font-sans text-text"
                dangerouslySetInnerHTML={{ __html: event.message }}
              />
              <span className="text-right text-[10px] text-text3">{event.meta ?? ''}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
