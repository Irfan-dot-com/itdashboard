import { cn } from '@/lib/utils/cn';

import { useSimulation } from '../useSimulation';

export function SimulationToggle() {
  const { running, toggle, elapsedSeconds } = useSimulation();

  return (
    <button
      type="button"
      onClick={toggle}
      title="Toggle live simulation"
      className={cn(
        'inline-flex items-center gap-2 rounded-[18px] border bg-surface px-2.5 py-1 text-[11px] font-medium text-text2 font-sans transition-colors',
        running
          ? 'border-green-dim bg-green-bg text-green'
          : 'border-border hover:border-border3',
      )}
    >
      <span
        className={cn(
          'h-1.5 w-1.5 rounded-full',
          running ? 'bg-green animate-pulse' : 'bg-text3',
        )}
      />
      <span>{running ? 'Live' : 'Static'}</span>
      <span className="font-mono text-[10px] opacity-85">{elapsedSeconds}s</span>
    </button>
  );
}
