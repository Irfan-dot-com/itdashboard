import { cn } from '@/lib/utils/cn';
import type { TickerSeverity } from '@/models';

import { useSimulation } from '../useSimulation';

const borderClass: Record<TickerSeverity, string> = {
  info: 'border-l-blue',
  ok: 'border-l-green',
  warn: 'border-l-amber',
  crit: 'border-l-red',
  agent: 'border-l-teal',
};

export function FloatAlerts() {
  const { floats, dismissFloat } = useSimulation();

  if (floats.length === 0) return null;

  return (
    <div className="pointer-events-none fixed right-6 top-20 z-[100] flex w-[340px] flex-col gap-2.5">
      {floats.map((float) => (
        <div
          key={float.id}
          role="button"
          tabIndex={0}
          onClick={() => dismissFloat(float.id)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') dismissFloat(float.id);
          }}
          className={cn(
            'pointer-events-auto cursor-pointer rounded-[8px] border border-border2 border-l-[3px] bg-surface p-3.5 text-xs shadow-[0_8px_28px_rgba(0,0,0,0.45)] animate-float-in',
            borderClass[float.type],
          )}
        >
          <div className="mb-1.5 text-[13px] font-semibold leading-tight text-text">{float.title}</div>
          <div
            className="text-[11.5px] leading-relaxed text-text2"
            dangerouslySetInnerHTML={{ __html: float.body }}
          />
          <div className="mt-2.5 flex items-center justify-between border-t border-border pt-2 font-mono text-[10px] text-text3">
            <span>{float.meta ?? ''}</span>
            <span className="font-sans font-semibold uppercase tracking-wide text-teal">Acknowledge</span>
          </div>
        </div>
      ))}
    </div>
  );
}
