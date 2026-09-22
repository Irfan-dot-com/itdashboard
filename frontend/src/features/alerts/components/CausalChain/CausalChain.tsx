import { Chip, Panel } from '@/components/ui';
import type { CausalChainEntry } from '@/models';

interface CausalChainProps {
  entries: CausalChainEntry[];
}

export function CausalChain({ entries }: CausalChainProps) {
  return (
    <Panel
      title={
        <>
          <span className="flex h-4.5 w-4.5 items-center justify-center rounded border border-border2 bg-surface2 text-text2" style={{ height: 18, width: 18 }}>
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.4} className="h-3 w-3">
              <circle cx="4" cy="4" r="2" />
              <circle cx="12" cy="12" r="2" />
              <path d="M5.5 5.5l5 5" />
            </svg>
          </span>
          Causal chain
        </>
      }
      actions={<Chip tone="dim">{entries.length} tiers</Chip>}
      bodyClassName="p-4"
    >
      <div className="flex flex-col">
        {entries.map((entry, index) => (
          <div
            key={entry.tier}
            className="grid grid-cols-[140px_1fr] gap-3.5 border-b border-border py-3.5 last:border-b-0"
          >
            <div className="flex items-center gap-2 text-[10.5px] font-medium uppercase tracking-wider text-text3">
              <span className="flex h-4.5 w-4.5 items-center justify-center rounded-full border border-border2 bg-surface2 font-mono text-[10px] text-text2" style={{ height: 18, width: 18 }}>
                {index + 1}
              </span>
              {entry.tierLabel}
            </div>
            <div>
              <div className="mb-1 text-[13px] font-medium">{entry.title}</div>
              <div className="text-xs leading-relaxed text-text2">{entry.description}</div>
              <div className="mt-1.5 flex flex-wrap gap-2.5 font-mono text-[10.5px] text-text3">
                {entry.metaItems.map((meta) => (
                  <span key={meta}>{meta}</span>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}
