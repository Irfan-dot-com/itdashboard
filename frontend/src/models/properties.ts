import type { HealthGrade } from './common';

export interface SiteAlertCounts {
  p1: number;
  p2: number;
  p3: number;
}

export interface PropertySummary {
  id: string;
  name: string;
  meta: string;
  score: number;
  grade: HealthGrade;
  alerts: SiteAlertCounts;
  worst: string;
  worstSig: string;
  spark: number[];
}
