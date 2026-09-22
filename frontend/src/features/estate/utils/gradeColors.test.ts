import { describe, expect, it } from 'vitest';

import { gradeColor, scoreColorClass, scoreTone } from './gradeColors';

describe('estate grade utilities', () => {
  it('maps grades to colors', () => {
    expect(gradeColor('crit')).toBe('#e85a4f');
    expect(gradeColor('warn')).toBe('#e0a62a');
    expect(gradeColor('ok')).toBe('#7fb849');
  });

  it('classifies score tone', () => {
    expect(scoreTone(40)).toBe('crit');
    expect(scoreTone(70)).toBe('warn');
    expect(scoreTone(90)).toBe('ok');
  });

  it('maps score to tailwind class', () => {
    expect(scoreColorClass(40)).toBe('text-red');
    expect(scoreColorClass(70)).toBe('text-amber');
    expect(scoreColorClass(90)).toBe('text-green');
  });
});
