export interface LuminaSuggestion {
  question: string;
  category: string;
}

export interface LuminaDataRow {
  label: string;
  value: string;
}

export interface LuminaAnswer {
  source: string;
  paragraph: string;
  rows: LuminaDataRow[];
  followUp?: string;
}

export const LUMINA_SUGGESTIONS: LuminaSuggestion[] = [
  { question: 'Which devices are flapping the most this week?', category: 'diagnostic' },
  { question: "What's our MTTR trend?", category: 'trend' },
  { question: 'Which integration has been dormant longest?', category: 'operations' },
  { question: 'What did agents auto-fix today?', category: 'agent' },
  { question: 'Show wake-up call failures across the estate', category: 'SLA' },
  { question: 'Which property has the most open P1 alerts?', category: 'severity' },
];

interface LuminaRule {
  pattern: RegExp;
  answer: LuminaAnswer;
}

const LUMINA_RULES: LuminaRule[] = [
  {
    pattern: /(devices?).*(flap|flapping|flap.*most)/i,
    answer: {
      source: 'Lumina · device diagnostic',
      paragraph:
        'Three devices account for 78% of port flaps this week. All Aruba CX edge switches; the pattern is concentrated to specific PoE ports serving DECT base stations.',
      rows: [
        { label: 'sw-edge-01 · Cottons', value: '14 flaps · port 1/0/14' },
        { label: 'sw-edge-03 · Aztec', value: '9 flaps · port 1/0/22' },
        { label: 'sw-edge-02 · Langdale', value: '6 flaps · port 1/0/08' },
        { label: 'All other devices combined', value: '8 flaps' },
      ],
      followUp:
        'Pattern: all three are PoE-budget-pressed and serve DECT base stations on EoL firmware. The agentic layer suggests coordinated firmware refresh would close the issue.',
    },
  },
  {
    pattern: /(MTTR|mean time|resolve).*(trend|over)|MTTR/i,
    answer: {
      source: 'Lumina · MTTR trend',
      paragraph:
        'Estate MTTR has improved from 38 to 22 minutes over the last 90 days, driven entirely by agent auto-fix on PoE/DECT issues. P2 MTTR is steady at ~45 min.',
      rows: [
        { label: 'P1 (now)', value: '22 min · target ≤ 30' },
        { label: 'P1 (90d ago)', value: '38 min' },
        { label: 'P2 (now)', value: '45 min' },
        { label: '% auto-fixed', value: '62% of P1' },
      ],
    },
  },
  {
    pattern: /(integration|interface).*(dormant|silent|long)/i,
    answer: {
      source: 'Lumina · integration health',
      paragraph:
        'Three integrations have been dormant longer than expected. The longest is the legacy CRM API at 14 days — recommended for decommissioning.',
      rows: [
        { label: 'Legacy CRM API', value: '14 days · decommission?' },
        { label: 'BMS link · Aztec', value: '2h 14m · investigating' },
        { label: 'Door lock API · Langdale', value: '1h 8m · normal pattern' },
      ],
    },
  },
  {
    pattern: /(agent|sadie|mike|henry).*(auto.?fix|fix|today|did)/i,
    answer: {
      source: 'Lumina · agent activity',
      paragraph:
        'Agents have auto-fixed 14 issues today across the estate, all within authority. The most consequential was a coordinated DECT recovery at Cottons.',
      rows: [
        { label: 'PoE port resets', value: '9 · all successful' },
        { label: 'Maintenance auto-routed', value: '11 tickets' },
        { label: 'Service decisions', value: '1,472 (Sadie)' },
        { label: 'Escalated to humans', value: '3' },
      ],
    },
  },
  {
    pattern: /(wake.?up).*(fail|failure|across)/i,
    answer: {
      source: 'Lumina · wake-up SLA',
      paragraph:
        'Wake-up SLA is 97.2% across the estate on a 98% target — slightly under but driven entirely by Langdale (86.1%). Six other properties are passing.',
      rows: [
        { label: 'Langdale', value: '86.1% · BREACH · DECT linkage' },
        { label: 'Group total', value: '97.2% · WATCH' },
        { label: 'Six other properties', value: '99.0–100%' },
      ],
    },
  },
  {
    pattern: /(P1|priority.?1|severity.?1|most.*open|alerts.*property)/i,
    answer: {
      source: 'Lumina · alert distribution',
      paragraph:
        'Cottons has the most open P1 alerts (1), followed by Langdale (1) and Aztec (1). All three were auto-triaged within 30 seconds.',
      rows: [
        { label: 'Cottons', value: '1 P1 · DECT regs' },
        { label: 'Langdale', value: '1 P1 · PMS link' },
        { label: 'Aztec', value: '1 P1 · door lock' },
        { label: 'P2 across estate', value: '4' },
      ],
    },
  },
];

export function getLuminaAnswer(query: string): LuminaAnswer {
  const match = LUMINA_RULES.find((rule) => rule.pattern.test(query));
  if (match) return match.answer;
  return {
    source: 'Lumina',
    paragraph:
      "I don't have a specific answer to that yet. Try asking about port flaps, MTTR trend, dormant integrations, agent auto-fixes today, wake-up failures, or P1 alert distribution.",
    rows: [],
  };
}
