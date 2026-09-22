import { Chip, StatusDot } from '@/components/ui';
import { formatRelative } from '@/lib/utils/date';
import type { AlertDetail } from '@/models';

interface AlertHeroProps {
  alert: AlertDetail;
}

export function AlertHero({ alert }: AlertHeroProps) {
  return (
    <div className="relative mb-3.5 overflow-hidden rounded-token-lg border border-border border-l-[3px] border-l-red bg-gradient-to-b from-surface to-surface2 px-5 py-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Chip tone="red">
          <StatusDot tone="red" pulsing />
          P1 · Critical
        </Chip>
        <Chip tone="dim">{alert.id.toUpperCase()}</Chip>
        <span className="agent-tag">Agent triaged</span>
        <Chip tone="teal">Auto-fix authorized</Chip>
        <span className="ml-auto font-mono text-[11px] text-text3">
          opened · {formatRelative(alert.openedAtIso)}
        </span>
      </div>
      <h1 className="mb-1.5 text-lg font-medium leading-snug tracking-tight">{alert.title}</h1>
      <div className="flex flex-wrap gap-3.5 text-[11.5px] text-text2">
        <div className="flex items-center gap-1.5">
          <span className="text-text3">Site</span>
          <span className="font-medium text-text">{alert.site}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-text3">Device</span>
          <span className="font-mono text-[11.5px] font-medium text-text">{alert.deviceFqdn}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-text3">Class</span>
          <span className="font-medium text-text">{alert.deviceClass}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-text3">Owner</span>
          <span className="font-medium text-text">{alert.owner}</span>
        </div>
      </div>
    </div>
  );
}
