import type { HTMLAttributes, ReactNode } from 'react';

import { cn } from '@/lib/utils/cn';

type ChipTone = 'default' | 'red' | 'amber' | 'green' | 'blue' | 'teal' | 'dim';

interface ChipProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: ChipTone;
  children: ReactNode;
}

const toneClass: Record<ChipTone, string> = {
  default: '',
  red: 'chip-red',
  amber: 'chip-amber',
  green: 'chip-green',
  blue: 'chip-blue',
  teal: 'chip-teal',
  dim: 'chip-dim',
};

export function Chip({ tone = 'default', className, children, ...rest }: ChipProps) {
  return (
    <span className={cn('chip', toneClass[tone], className)} {...rest}>
      {children}
    </span>
  );
}
