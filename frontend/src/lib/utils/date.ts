export function formatClock(date: Date = new Date()): string {
  return date.toTimeString().slice(0, 8);
}

export function formatRelative(fromIso: string, now: Date = new Date()): string {
  const then = new Date(fromIso).getTime();
  const diffMs = now.getTime() - then;
  const minutes = Math.round(diffMs / 60_000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}
