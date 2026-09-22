import type { AlertDetail, AlertSummary } from '@/models';

/** Matches `page-alerts` in it_dashboard.html · severity-sorted. */
export const ALERT_FIXTURES: AlertSummary[] = [
  {
    id: 'ALR-2026-0419-0731',
    severity: 'p1',
    time: '17:31',
    site: 'Cottons',
    summary: 'DECT registrations dropped — reception PHB',
    detail: 'NetOps auto-triage · reception hunt group degraded',
    triagedBy: 'NetOps (auto-triaged)',
    agent: true,
    impact: '£540/hr',
    impactLabel: 'rev exposure',
  },
  {
    id: 'ALR-2026-0419-0728',
    severity: 'p1',
    time: '17:00',
    site: 'Langdale',
    summary: 'PMS link heartbeat-only · 14 events queued',
    detail: 'GuestLine · no events · check-ins not posted',
    triagedBy: 'NetOps (auto-triaged)',
    agent: true,
    impact: '14 rooms',
    impactLabel: 'unposted',
  },
  {
    id: 'ALR-2026-0419-0724',
    severity: 'p1',
    time: '04:18',
    site: 'Aztec',
    summary: 'Door lock unresponsive — room 115',
    detail: 'Salto Neo hub · retries exhausted',
    triagedBy: 'FacilityOps',
    agent: false,
  },
  {
    id: 'ALR-2026-0419-0719',
    severity: 'p2',
    time: '15:28',
    site: 'Aztec',
    summary: 'BMS heartbeat-only · 2h 14m',
    detail: 'Trend IQ4 · occupancy signal stale',
    triagedBy: 'FacilityOps',
    agent: false,
  },
  {
    id: 'ALR-2026-0419-0717',
    severity: 'p2',
    time: 'yesterday',
    site: 'Cottons',
    summary: 'Reception answer rate below brand · 3 days',
    detail: 'Rolling 72h SLA · Sadie playbook',
    triagedBy: 'Sadie escalation',
    agent: true,
  },
  {
    id: 'ALR-2026-0419-0712',
    severity: 'p2',
    time: '15:08',
    site: 'Langdale',
    summary: 'Wake-up SLA breach risk · 6 failures today',
    detail: 'Unassigned queue · escalate on next failure',
    triagedBy: '(unassigned)',
    agent: false,
  },
  {
    id: 'ALR-2026-0419-0709',
    severity: 'p2',
    time: '14:42',
    site: 'Cottons',
    summary: 'PoE port flap storm · sw-edge-01',
    detail: 'Aruba CX · VLAN edge · flap count exceeded',
    triagedBy: 'NetOps',
    agent: true,
  },
];

/** Baseline detail for Cottons DECT / port flap (worked example). */
export const ALERT_DETAIL_FIXTURE: AlertDetail = {
  id: 'ALR-2026-0419-0731',
  severity: 'p1',
  title: 'DECT registrations dropped 12 → 4 at Cottons Hotel Reception',
  site: 'Cottons Hotel',
  deviceFqdn: 'dect-bs-04.cottons.thwaites.local',
  deviceClass: 'DECT base station',
  owner: 'A. Hollet (on-call)',
  openedAtIso: new Date(Date.now() - 11 * 60_000).toISOString(),
  chain: [
    {
      tier: 'element',
      tierLabel: 'Element',
      title: 'PoE switch port flapping',
      description:
        'Port 1/0/14 on sw-edge-01.cottons has flapped 4 times in the last 11 minutes. Power negotiation failing on each retry. Upstream PoE budget healthy (38W of 720W).',
      metaItems: ['last flap 17:39:42', 'uptime 14d', 'vendor: Aruba CX 6300'],
    },
    {
      tier: 'signal',
      tierLabel: 'Signal',
      title: 'SIP registrations dropped from 12 to 4',
      description:
        'DECT base station dect-bs-04 lost power-cycle handshake; 8 of 12 handsets failed to re-register on the BroadSoft cluster. Baseline for Tuesday 17:30 is 11.8 ± 0.4 registrations.',
      metaItems: ['deviation: −7.8σ', 'baseline window: 12w · same hour'],
    },
    {
      tier: 'business',
      tierLabel: 'Business KPI',
      title: 'Reception answer rate degrading',
      description:
        'External call answer rate at Cottons fallen from 78% to 41% in the last 9 minutes. Currently 6 of last 14 calls deflected to voicemail; baseline is <1 in 10. Hunt group 601 → Reservations bypassing 4 unreachable handsets.',
      metaItems: ['since 17:33', '14 calls · 6 to VM'],
    },
    {
      tier: 'consequence',
      tierLabel: 'Consequence',
      title: 'Direct booking risk · est. £180–340 per hour',
      description:
        'Cottons reservations team unreachable on incoming bookings. Historical conversion data: 1 in 3 voicemail-deflected booking calls do not call back. Estimated revenue exposure if unresolved by 18:00 = £540 (90% CI £180–940).',
      metaItems: ['model: gbm-revenue-v3', 'confidence 0.78'],
    },
  ],
  reasoning: {
    body:
      'Pattern matches a recurring fault on this exact port — 2026-02-11 14:22 and 2025-11-08 09:45 both showed the same signature: DECT base station power-renegotiation failure following an 802.3at LLDP refresh. In both cases a port power-cycle resolved within 90 seconds without follow-up. PoE chip on the base unit is approaching its 4-year MTBF; recommend hardware replacement within 30 days.',
    confidence: 0.84,
    matchedEvents: 2,
    tokensUsed: 2840,
  },
  runbook: [
    { step: 'Port flap detected on sw-edge-01:1/0/14 (signal threshold)', status: 'done', time: '17:31:08' },
    { step: 'Agent ingested 12w baseline, classified as known pattern', status: 'done', time: '17:31:14' },
    { step: 'Causal chain assembled (4 tiers · revenue model attached)', status: 'done', time: '17:31:18' },
    { step: 'Severity raised P2 → P1 on KPI breach (answer rate <50%)', status: 'done', time: '17:33:50' },
    { step: 'On-call notified: A. Hollet (SMS · push)', status: 'done', time: '17:34:02' },
    { step: 'Awaiting auto-fix authorization or human override', status: 'pending', time: '—' },
  ],
};

/** MSW / tests: approximate detail payload when opening any list row. */
export function mergeAlertDetail(alertId: string): AlertDetail {
  const row = ALERT_FIXTURES.find((a) => a.id === alertId);
  if (!row) {
    return { ...ALERT_DETAIL_FIXTURE, id: alertId };
  }
  const siteLabel = row.site.includes('Hotel') ? row.site : `${row.site} Hotel`;
  return {
    ...ALERT_DETAIL_FIXTURE,
    id: row.id,
    severity: row.severity,
    site: siteLabel,
    title:
      row.severity === 'p1'
        ? `${row.summary} — ${siteLabel}`
        : `${row.summary} · ${siteLabel}`,
  };
}
