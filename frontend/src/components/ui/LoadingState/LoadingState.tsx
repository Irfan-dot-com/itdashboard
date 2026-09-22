interface LoadingStateProps {
  label?: string;
}

export function LoadingState({ label = 'Loading…' }: LoadingStateProps) {
  return (
    <div className="rounded-token-lg border border-border bg-surface p-8 text-center text-xs text-text3 animate-pulse">
      {label}
    </div>
  );
}
