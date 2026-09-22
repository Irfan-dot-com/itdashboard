import type { HealthGrade } from '@/models';

export function gradeColor(grade: HealthGrade): string {
  if (grade === 'crit') return '#e85a4f';
  if (grade === 'warn') return '#e0a62a';
  return '#7fb849';
}

export function scoreTone(score: number): HealthGrade {
  if (score < 60) return 'crit';
  if (score < 85) return 'warn';
  return 'ok';
}

export function scoreColorClass(score: number): string {
  const grade = scoreTone(score);
  if (grade === 'crit') return 'text-red';
  if (grade === 'warn') return 'text-amber';
  return 'text-green';
}
