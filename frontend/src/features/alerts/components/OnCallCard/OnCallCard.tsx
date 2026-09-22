import { Panel } from '@/components/ui';

interface OnCallEntry {
  initials: string;
  name: string;
  role: string;
  status: string;
  statusTone?: 'ok' | 'neutral';
  avatarTone?: 'ok' | 'neutral' | 'subtle';
}

const ENTRIES: OnCallEntry[] = [
  { initials: 'AH', name: 'A. Hollet', role: 'Primary · Cottons site', status: 'ack 1m ago', statusTone: 'ok', avatarTone: 'ok' },
  { initials: 'JM', name: 'J. Makin', role: 'Secondary · group', status: 'notified', statusTone: 'neutral', avatarTone: 'neutral' },
  { initials: 'MS', name: 'MSP — Bynet', role: 'Escalation · 30m timer', status: 'standby', statusTone: 'neutral', avatarTone: 'subtle' },
];

const avatarClass: Record<NonNullable<OnCallEntry['avatarTone']>, string> = {
  ok: 'bg-green-bg text-green border-green-dim',
  neutral: 'bg-surface3 text-text2 border-border2',
  subtle: 'bg-surface3 text-text2 border-border2',
};

const statusClass: Record<NonNullable<OnCallEntry['statusTone']>, string> = {
  ok: 'text-green',
  neutral: 'text-text3',
};

export function OnCallCard() {
  return (
    <Panel title="On-call" bodyClassName="p-0" className="mt-3.5">
      <div className="flex flex-col">
        {ENTRIES.map((entry) => (
          <div key={entry.name} className="flex items-center gap-2.5 border-b border-border px-4 py-2.5 last:border-b-0">
            <div className={`flex h-6 w-6 items-center justify-center rounded-full border font-mono text-[10px] font-medium ${avatarClass[entry.avatarTone ?? 'neutral']}`}>
              {entry.initials}
            </div>
            <div className="flex-1">
              <div className="text-xs font-medium">{entry.name}</div>
              <div className="text-[10.5px] text-text3">{entry.role}</div>
            </div>
            <span className={`font-mono text-[10.5px] ${statusClass[entry.statusTone ?? 'neutral']}`}>
              {entry.status}
            </span>
          </div>
        ))}
      </div>
    </Panel>
  );
}
