import { useEffect, useState } from 'react';

import { formatClock } from '@/lib/utils/date';

export function useClock(): string {
  const [time, setTime] = useState(() => formatClock());

  useEffect(() => {
    const interval = window.setInterval(() => setTime(formatClock()), 1000);
    return () => window.clearInterval(interval);
  }, []);

  return time;
}
