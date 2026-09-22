import type { EstateKpi, ExecKpi } from '@/models';

export const ESTATE_KPIS: EstateKpi[] = [
  { id: 'health', label: 'Estate health', value: '87.4', tone: 'warn', trend: '▼ 4.2 vs 7d avg' },
  { id: 'online', label: 'Sites online', value: '6/7', tone: 'ok', trend: 'Langdale degraded' },
  { id: 'p1', label: 'Open P1', value: '3', tone: 'crit', trend: '2 acknowledged' },
  { id: 'mttr', label: 'MTTR (24h)', value: '22m', tone: 'neutral', trend: '▲ within target' },
  { id: 'autofix', label: 'Agent auto-fix', value: '94%', tone: 'ok', trend: '17 of 18 today' },
  { id: 'wakeup', label: 'Wake-up SLA', value: '93.6%', tone: 'warn', trend: 'target 98%' },
];

export const EXEC_KPIS: ExecKpi[] = [
  {
    id: 'uptime',
    label: 'Estate uptime',
    value: '99.42%',
    tone: 'ok',
    delta: '▲ 0.18 pp vs Q4 · target 99.5%',
    spark: [99.1, 99.0, 99.2, 99.3, 99.2, 99.4, 99.4, 99.5, 99.4, 99.4, 99.4, 99.42],
    color: '#7fb849',
  },
  {
    id: 'mttr',
    label: 'MTTR · P1',
    value: '38m',
    tone: 'neutral',
    delta: '▼ 22m vs Q4 · agent layer impact',
    spark: [62, 58, 55, 52, 48, 45, 42, 40, 39, 38, 38, 38],
    color: '#5b9fd6',
  },
  {
    id: 'cost',
    label: 'Cost of IT-driven loss',
    value: '£14.2k',
    tone: 'warn',
    delta: '▼ £8.1k vs Q4 · prevented £42k',
    spark: [28, 24, 22, 21, 19, 17, 16, 16, 15, 14, 14, 14.2],
    color: '#e0a62a',
  },
  {
    id: 'debt',
    label: 'Technical debt index',
    value: '62/100',
    tone: 'crit',
    delta: '▲ 4 · 3 dormant integrations',
    spark: [54, 55, 56, 58, 59, 60, 61, 61, 62, 62, 62, 62],
    color: '#e85a4f',
  },
];
