import type { HTMLAttributes, ReactNode } from 'react';

import { cn } from '@/lib/utils/cn';

interface PanelProps extends Omit<HTMLAttributes<HTMLDivElement>, 'title'> {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  bodyClassName?: string;
  children: ReactNode;
}

export function Panel({ title, subtitle, actions, className, bodyClassName, children, ...rest }: PanelProps) {
  return (
    <div
      className={cn(
        'overflow-hidden rounded-token-lg border border-border bg-surface',
        className,
      )}
      {...rest}
    >
      {(title || actions) && (
        <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
          <div>
            <div className="text-[12.5px] font-medium flex items-center gap-2">{title}</div>
            {subtitle ? <div className="text-[10.5px] text-text3 mt-0.5">{subtitle}</div> : null}
          </div>
          {actions ? <div className="flex items-center gap-1.5">{actions}</div> : null}
        </div>
      )}
      <div className={cn('p-4', bodyClassName)}>{children}</div>
    </div>
  );
}
