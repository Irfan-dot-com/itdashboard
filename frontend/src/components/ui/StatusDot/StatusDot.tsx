import { cn } from '@/lib/utils/cn';

type Tone = 'red' | 'amber' | 'green' | 'gray';

interface StatusDotProps {
  tone: Tone;
  pulsing?: boolean;
  className?: string;
}

const toneClass: Record<Tone, string> = {
  red: 'dot-red',
  amber: 'dot-amber',
  green: 'dot-green',
  gray: 'dot-gray',
};

export function StatusDot({ tone, pulsing, className }: StatusDotProps) {
  return <span className={cn('dot', toneClass[tone], pulsing && 'dot-pulsing', className)} />;
}
