import { BarChart } from '@/components/charts';

const LABELS = ['Mar 1', 'Mar 8', 'Mar 15', 'Mar 22', 'Mar 29', 'Apr 5', 'Apr 12', 'Apr 19'];
const AUTO = [62, 71, 68, 79, 82, 84, 91, 94];
const ESCALATED = [22, 18, 21, 17, 16, 18, 15, 12];

export function AgentActivityChart() {
  return (
    <div className="rounded-token-lg border border-border bg-surface p-4">
      <div className="mb-3.5 flex items-start justify-between">
        <div>
          <div className="text-[11px] font-medium uppercase tracking-wider text-text3">
            Agent activity · last 90 days
          </div>
          <div className="mt-1 text-[11.5px] text-text2">Auto-resolved incidents and triage summaries</div>
        </div>
        <span className="agent-tag">Active</span>
      </div>
      <div className="grid grid-cols-4 gap-px overflow-hidden rounded-token bg-border">
        <Cell label="Auto-resolved" value="847" tone="text-green" sub="~ 9.4/day" />
        <Cell label="Triaged · escalated" value="214" sub="human acted" />
        <Cell label="False positive" value="11" tone="text-amber" sub="1.0% rate" />
        <Cell label="Labor displaced" value="312h" sub="~ £8.7k saved" />
      </div>
      <div className="relative mt-3 h-24">
        <BarChart
          labels={LABELS}
          datasets={[
            { label: 'Auto-resolved', data: AUTO, color: '#3ec1a4' },
            { label: 'Escalated', data: ESCALATED, color: '#6e6a5e' },
          ]}
          ariaLabel="Agent activity over 90 days"
        />
      </div>
    </div>
  );
}

function Cell({ label, value, sub, tone }: { label: string; value: string; sub: string; tone?: string }) {
  return (
    <div className="bg-surface px-3 py-2.5">
      <div className="text-[10.5px] font-medium uppercase tracking-wider text-text3">{label}</div>
      <div className={`mt-1 font-mono text-lg font-medium ${tone ?? ''}`}>{value}</div>
      <div className="text-[10.5px] text-text3">{sub}</div>
    </div>
  );
}
