import type { ReactNode } from 'react';

import { env } from '@/lib/env/env';

import { Sidebar } from '../Sidebar';

interface AppShellProps {
  children: ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="grid min-h-screen grid-cols-[212px_1fr] max-md:grid-cols-1 max-md:[&>aside]:hidden">
      <Sidebar />
      <div className="flex min-w-0 flex-col">
        {children}
        <footer className="flex items-center justify-between border-t border-border px-5 py-3 font-mono text-[10.5px] text-text3">
          <span>estate-it · {env.releaseVersion} · {env.appEnv}</span>
          <span>{env.appName}</span>
        </footer>
      </div>
    </div>
  );
}
