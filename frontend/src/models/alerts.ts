import type { Severity } from './common';

export interface AlertSummary {
  id: string;
  severity: Severity;
  time: string;
  site: string;
  summary: string;
  detail: string;
  /** Who triaged or owns the alert row (full alerts table). */
  triagedBy: string;
  impact?: string;
  impactLabel?: string;
  agent: boolean;
}

export type ChainTier = 'element' | 'signal' | 'business' | 'consequence';

export interface CausalChainEntry {
  tier: ChainTier;
  tierLabel: string;
  title: string;
  description: string;
  metaItems: string[];
}

export interface AlertDetail {
  id: string;
  severity: Severity;
  title: string;
  site: string;
  deviceFqdn: string;
  deviceClass: string;
  owner: string;
  openedAtIso: string;
  chain: CausalChainEntry[];
  reasoning: {
    body: string;
    confidence: number;
    matchedEvents: number;
    tokensUsed: number;
  };
  runbook: { step: string; status: 'done' | 'pending'; time: string }[];
}
