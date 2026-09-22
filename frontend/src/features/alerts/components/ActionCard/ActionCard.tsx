import { Button } from '@/components/ui';

export function ActionCard() {
  return (
    <div className="sticky top-20 overflow-hidden rounded-token-lg border border-border bg-surface">
      <header className="border-b border-border px-4 pb-3 pt-3.5">
        <div className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-teal">Recommended action</div>
        <div className="mb-1.5 text-sm font-medium leading-snug">Power-cycle PoE port 1/0/14</div>
        <div className="text-[11.5px] leading-relaxed text-text2">
          Remote disable then re-enable on <span className="mono">sw-edge-01.cottons</span>. Forces DECT base station
          to re-handshake. Resolves 96% of matched cases.
        </div>
      </header>

      <div className="flex flex-col gap-1.5 border-b border-border px-4 py-2.5 text-[11px]">
        <Row label="ETA" value="~ 90 seconds" />
        <Row label="Blast radius" value="1 port · 0 calls active" />
        <Row label="Reversible" value="Yes" />
        <Row label="Match confidence" value="0.84" />
      </div>

      <div className="border-b border-border bg-surface2 px-4 py-3">
        <div className="flex items-center justify-between text-[11px]">
          <div className="flex items-center gap-1.5 text-green">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.6} className="h-3 w-3">
              <path d="M2 8l4 4 8-9" />
            </svg>
            <span>Pre-authorized for this device class</span>
          </div>
          <a className="text-[10.5px] text-text2 hover:text-text" href="#">
            Edit policy →
          </a>
        </div>
      </div>

      <div className="flex flex-col gap-2 px-4 py-3.5">
        <Button variant="prime" className="justify-center text-xs" icon={
          <svg viewBox="0 0 16 16" fill="currentColor" className="h-3 w-3">
            <path d="M3 3l10 5-10 5V3z" />
          </svg>
        }>
          Run auto-fix now
        </Button>
        <div className="mt-1 flex gap-1.5">
          <Button className="flex-1 text-[11px]">Run manually</Button>
          <Button className="flex-1 text-[11px]">Defer 5m</Button>
        </div>
        <Button variant="ghost" className="mt-2 justify-center text-[11px]">
          View runbook · 4 steps
        </Button>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-text3">{label}</span>
      <span className="font-mono text-text">{value}</span>
    </div>
  );
}
