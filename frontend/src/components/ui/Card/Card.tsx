import type { HTMLAttributes } from 'react';

import { cn } from '@/lib/utils/cn';

export function Card({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('rounded-token-lg border border-border bg-surface', className)}
      {...rest}
    />
  );
}
