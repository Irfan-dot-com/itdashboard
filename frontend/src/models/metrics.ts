export interface EstateKpi {
  id: string;
  label: string;
  value: string;
  trend?: string;
  tone?: 'ok' | 'warn' | 'crit' | 'neutral';
  suffix?: string;
}

export interface ExecKpi {
  id: string;
  label: string;
  value: string;
  delta?: string;
  tone?: 'ok' | 'warn' | 'crit' | 'neutral';
  spark: number[];
  color: string;
}
