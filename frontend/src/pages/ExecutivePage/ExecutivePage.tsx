import { Button } from '@/components/ui';
import { AgentActivityChart, ExecKpiGrid } from '@/features/executive';

export function ExecutivePage() {
  return (
    <div>
      <header className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[22px] font-medium leading-tight tracking-tight">Executive view</h1>
          <p className="mt-1 text-[12.5px] text-text2">
            Quarterly rollup · Q1 2026 vs Q4 2025 · Thwaites Group · 7 properties
          </p>
        </div>
        <div className="flex gap-1.5">
          <Button>Q1 2026</Button>
          <Button>vs Q4 2025</Button>
          <Button variant="prime">Export board pack</Button>
        </div>
      </header>

      <div className="flex flex-col gap-3">
        <ExecKpiGrid />
        <AgentActivityChart />
      </div>
    </div>
  );
}
