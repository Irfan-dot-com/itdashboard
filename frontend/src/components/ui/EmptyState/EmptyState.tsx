import type { ReactNode } from 'react';

interface EmptyStateProps {
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="rounded-token-lg border border-border bg-surface p-8 text-center">
      <div className="text-sm font-medium">{title}</div>
      {description ? <div className="mt-2 text-xs text-text2">{description}</div> : null}
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}
