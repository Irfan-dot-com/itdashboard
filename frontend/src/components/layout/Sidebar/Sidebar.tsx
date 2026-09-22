import { NavLink } from 'react-router-dom';

import { NAV_GROUPS } from '@/constants/navigation';
import { cn } from '@/lib/utils/cn';

const badgeClass: Record<string, string> = {
  red: 'bg-red-bg text-red border-red-dim',
  amber: 'bg-amber-bg text-amber border-amber-dim',
  ok: 'bg-green-bg text-green border-green-dim',
  live: 'bg-green-bg text-green border-green-dim',
};

export function Sidebar() {
  return (
    <aside className="sticky top-0 flex h-screen w-[212px] flex-col border-r border-border bg-surface pt-4 pb-3">
      <div className="border-b border-border px-4 pb-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-5.5 w-5.5 items-center justify-center rounded-[5px] bg-text font-mono text-xs font-semibold text-bg" style={{ height: 22, width: 22 }}>
            T
          </div>
          <div>
            <div className="text-[13px] font-medium tracking-tight">Estate IT</div>
          </div>
        </div>
        <div className="mt-2 text-[10.5px] font-medium uppercase tracking-wider text-text3">
          Thwaites · 7 sites
        </div>
      </div>

      <nav className="flex-1 px-2 pt-3 overflow-y-auto scrollbar-thin">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="mb-3.5">
            <div className="px-2.5 pb-1 pt-1.5 text-[10px] font-medium uppercase tracking-wider text-text3">
              {group.label}
            </div>
            {group.items.map((item) => (
              <NavLink
                key={item.key}
                to={item.path}
                end={item.path === '/'}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-2.5 rounded-token px-2.5 py-1.5 text-[12.5px] transition-colors select-none',
                    isActive
                      ? 'bg-surface3 text-text font-medium'
                      : 'text-text2 hover:bg-surface2 hover:text-text',
                  )
                }
              >
                <span className="text-text3 flex-shrink-0">{item.icon}</span>
                <span className="flex-1">{item.label}</span>
                {item.badge ? (
                  <span
                    className={cn(
                      'ml-auto inline-flex items-center gap-1 rounded-[9px] border px-1.5 py-[1px] font-mono text-[10px]',
                      badgeClass[item.badge.tone],
                    )}
                  >
                    {item.badge.tone === 'live' ? (
                      <span className="h-1 w-1 rounded-full bg-green animate-pulse" />
                    ) : null}
                    {item.badge.label}
                  </span>
                ) : null}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      <div className="border-t border-border px-3.5 py-2.5">
        <div className="flex items-center gap-2.5 rounded-token px-2 py-1.5">
          <div className="flex h-6 w-6 items-center justify-center rounded-full border border-border2 bg-surface3 font-mono text-[10px] font-medium text-text2">
            JM
          </div>
          <div>
            <div className="text-[11.5px] leading-tight">J. Makin</div>
            <div className="text-[10px] text-text3">Estate IT lead</div>
          </div>
        </div>
      </div>
    </aside>
  );
}
