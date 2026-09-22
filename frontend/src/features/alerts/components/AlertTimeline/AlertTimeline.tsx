import { Panel } from '@/components/ui';
import { cn } from '@/lib/utils/cn';
import type { AlertDetail } from '@/models';

interface AlertTimelineProps {
  runbook: AlertDetail['runbook'];
}

export function AlertTimeline({ runbook }: AlertTimelineProps) {
  return (
    <Panel title="Timeline" bodyClassName="p-0">
      <div className="flex flex-col">
        {runbook.map((entry, index) => (
          <div
            key={`${index}-${entry.step}`}
            className="flex items-center gap-2.5 border-b border-border px-4 py-2.5 text-[11.5px] last:border-b-0"
          >
            <span
              className={cn(
                'flex h-4.5 w-4.5 flex-shrink-0 items-center justify-center rounded-full border border-border2 bg-surface2 font-mono text-[10px] text-text2',
                entry.status === 'done' && 'border-teal-dim bg-teal-bg text-teal',
              )}
              style={{ height: 18, width: 18 }}
            >
              {index + 1}
            </span>
            <span className={cn('flex-1 text-text', entry.status === 'done' && 'text-text2')}>{entry.step}</span>
            <span className="font-mono text-[10.5px] text-text3">{entry.time}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}
