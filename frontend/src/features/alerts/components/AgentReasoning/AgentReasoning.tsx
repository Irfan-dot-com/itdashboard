import { Chip, Panel } from '@/components/ui';
import type { AlertDetail } from '@/models';

interface AgentReasoningProps {
  reasoning: AlertDetail['reasoning'];
}

export function AgentReasoning({ reasoning }: AgentReasoningProps) {
  return (
    <Panel
      title={
        <>
          <span className="flex h-4.5 w-4.5 items-center justify-center rounded border border-border2 bg-surface2 text-text2" style={{ height: 18, width: 18 }}>
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.4} className="h-3 w-3">
              <circle cx="8" cy="8" r="6" />
              <circle cx="8" cy="8" r="2.5" fill="currentColor" />
            </svg>
          </span>
          Agent reasoning
        </>
      }
      actions={<Chip tone="teal">Confidence {reasoning.confidence.toFixed(2)}</Chip>}
    >
      <div className="relative rounded-token border border-teal-dim bg-teal-bg p-3.5">
        <div className="mb-2 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-teal">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.4} className="h-3 w-3">
            <path d="M8 1v3M8 12v3M1 8h3M12 8h3M3 3l2 2M11 11l2 2M3 13l2-2M11 5l2-2" />
          </svg>
          Network-ops agent · diagnosis
        </div>
        <div className="text-xs leading-relaxed text-text">{reasoning.body}</div>
        <div className="mt-2 flex flex-wrap gap-3.5 border-t border-teal-dim pt-2 font-mono text-[10.5px] text-text2">
          <span>
            matched events: <strong className="font-medium text-text">{reasoning.matchedEvents}</strong>
          </span>
          <span>
            tokens: <strong className="font-medium text-text">{reasoning.tokensUsed.toLocaleString()}</strong>
          </span>
        </div>
      </div>
    </Panel>
  );
}
