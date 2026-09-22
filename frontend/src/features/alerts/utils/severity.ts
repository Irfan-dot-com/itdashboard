import type { Severity } from '@/models';

export function severityBarClass(severity: Severity): string {
  switch (severity) {
    case 'p1':
      return 'bg-red';
    case 'p2':
      return 'bg-amber';
    case 'p3':
      return 'bg-blue';
    case 'info':
    default:
      return 'bg-text4';
  }
}
