import type { SimulatedEventTrigger } from '@/models';

export const SIM_EVENTS: SimulatedEventTrigger[] = [
  {
    kind: 'continuous',
    event: {
      id: 'c1',
      severity: 'info',
      label: 'SIP',
      property: 'Solent',
      message: '<strong>SIP REGISTER</strong> dect-base-04 · 200 OK',
      meta: '15ms',
    },
  },
  {
    kind: 'continuous',
    event: {
      id: 'c2',
      severity: 'ok',
      label: 'CDR',
      property: 'Cottons',
      message: '<strong>Call ended</strong> ext 2014 → 9-44-1142… · MOS 4.3',
      meta: '4m 12s',
    },
  },
  {
    kind: 'continuous',
    event: {
      id: 'c3',
      severity: 'info',
      label: 'PMS',
      property: 'Aztec',
      message: '<strong>Check-in</strong> room 218 · BroadSoft posted',
      meta: 'OK',
    },
  },
  {
    kind: 'continuous',
    event: {
      id: 'c4',
      severity: 'agent',
      label: 'AGENT',
      property: 'Cottons',
      message: '<strong>Sadie</strong> handled out-of-hours request · room 412',
      meta: '+0s',
    },
  },
  {
    kind: 'continuous',
    event: {
      id: 'c5',
      severity: 'info',
      label: 'PMS',
      property: 'Solent',
      message: '<strong>Wake-up scheduled</strong> room 307 for 06:30',
      meta: 'OK',
    },
  },
  {
    kind: 'continuous',
    event: {
      id: 'c6',
      severity: 'ok',
      label: 'SYS',
      property: 'Kettering',
      message: '<strong>BMS heartbeat</strong> trend-iq4-01 · within bounds',
      meta: '2s',
    },
  },
  {
    kind: 'timed',
    offsetMs: 7000,
    event: {
      id: 't1',
      severity: 'warn',
      label: 'SIP',
      property: 'Cottons',
      message:
        '<strong>SIP REGISTER fail</strong> dect-base-02 · 401 unauthorized · attempt 3',
      meta: '+2.4σ',
    },
    float: {
      type: 'warn',
      title: 'DECT registration anomaly',
      body: 'Three SIP REGISTER 401s within 90 seconds at <strong>Cottons</strong> · dect-base-02 · likely PoE port issue. Net-ops will auto-investigate.',
      meta: 'Cottons · 17:42 · Watch',
    },
  },
  {
    kind: 'timed',
    offsetMs: 14000,
    event: {
      id: 't2',
      severity: 'warn',
      label: 'SYS',
      property: 'Cottons',
      message:
        '<strong>PoE port flap storm</strong> sw-edge-01 1/0/14 · 3 cycles in 10min',
      meta: '+3.1σ',
    },
  },
  {
    kind: 'timed',
    offsetMs: 20000,
    event: {
      id: 't3',
      severity: 'agent',
      label: 'AGENT',
      property: 'Cottons',
      message:
        '<strong>Net-ops auto-fix</strong> power-cycled sw-edge-01 port 1/0/14 · per policy',
      meta: 'authorized',
    },
    float: {
      type: 'agent',
      title: 'Auto-fix · Net-ops',
      body: '<strong>Net-ops</strong> power-cycled sw-edge-01 port 1/0/14 (DECT base PoE budget). Authorized by policy <code>netops.port_cycle v1.1.0</code>. Recovery in progress.',
      meta: 'Cottons · 17:43 · Auto-fix',
    },
  },
  {
    kind: 'timed',
    offsetMs: 27000,
    event: {
      id: 't4',
      severity: 'ok',
      label: 'SIP',
      property: 'Cottons',
      message:
        '<strong>SIP REGISTER recovered</strong> dect-base-02 · 200 OK · 15ms',
      meta: 'fixed',
    },
  },
  {
    kind: 'timed',
    offsetMs: 34000,
    event: {
      id: 't5',
      severity: 'crit',
      label: 'PMS',
      property: 'Langdale',
      message:
        '<strong>PMS link silent</strong> GuestLine · no events &gt; 30 min · alert opened',
      meta: '+5.8σ',
    },
    float: {
      type: 'crit',
      title: 'P1 · Langdale PMS Link',
      body: 'GuestLine PMS link is heartbeat-only since 17:00. <strong>14 check-ins not posted to PBX.</strong> Auto-triaged to NetOps; estimated restoration 90 min.',
      meta: 'Langdale · 17:45 · P1',
    },
  },
];
