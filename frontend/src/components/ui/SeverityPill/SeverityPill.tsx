import type { ReactNode } from 'react';

import { cn } from '@/lib/utils/cn';

type Tone = 'crit' | 'warn' | 'info' | 'ok' | 'agent';

interface SeverityPillProps {
  tone: Tone;
  children: ReactNode;
  className?: string;
}

const toneClass: Record<Tone, string> = {
  crit: 'sev-pill-crit',
  warn: 'sev-pill-warn',
  info: 'sev-pill-info',
  ok: 'sev-pill-ok',
  agent: 'sev-pill-agent',
};

export function SeverityPill({ tone, children, className }: SeverityPillProps) {
  return <span className={cn('sev-pill', toneClass[tone], className)}>{children}</span>;
}
