import type { ReactNode } from 'react';

import { useClock } from '@/hooks/useClock';
import { useTheme } from '@/hooks/useTheme';
import { LuminaBar } from '@/features/lumina';
import { SimulationToggle } from '@/features/simulation';

interface TopbarProps {
  breadcrumbs: ReactNode;
}

export function Topbar({ breadcrumbs }: TopbarProps) {
  const { toggleTheme } = useTheme();
  const time = useClock();

  return (
    <div className="sticky top-0 z-[5] flex items-center justify-between gap-3.5 border-b border-border bg-bg px-5 py-2.5">
      <div className="min-w-0 flex-shrink-0">{breadcrumbs}</div>
      <LuminaBar />
      <div className="flex items-center gap-2.5">
        <SimulationToggle />
        <button
          type="button"
          aria-label="Notifications"
          className="flex h-7 w-7 items-center justify-center rounded-token border border-transparent text-text2 hover:bg-surface hover:text-text hover:border-border"
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.4}>
            <path d="M3 12V8a5 5 0 1110 0v4l1 1H2l1-1z" />
            <path d="M6.5 14a1.5 1.5 0 003 0" />
          </svg>
        </button>
        <button
          type="button"
          aria-label="Toggle theme"
          onClick={toggleTheme}
          className="flex h-7 w-7 items-center justify-center rounded-token border border-transparent text-text2 hover:bg-surface hover:text-text hover:border-border"
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.4}>
            <path d="M13 9.5A5 5 0 016.5 3a5 5 0 100 10 5 5 0 006.5-3.5z" />
          </svg>
        </button>
        <div className="rounded-[14px] border border-border bg-surface px-2.5 py-1 font-mono text-[11px] text-text2">
          {time}
        </div>
      </div>
    </div>
  );
}
