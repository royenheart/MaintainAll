import { describe, expect, it } from 'vitest';
import {
  cardWindow,
  stepBoundCard,
} from '../../src/explorations/orbit/bound-card-sequence';

describe('bound card window', () => {
  it('never duplicates or shows more than three cards, including around the seam', () => {
    for (const count of [0, 1, 2, 3, 8, 100])
      for (let index = 0; index < Math.max(count, 1); index++) {
        const visible = cardWindow(index, count);
        expect(visible.length).toBe(Math.min(3, count));
        expect(new Set(visible).size).toBe(visible.length);
        if (count) expect(visible[0]).toBe(index);
      }
  });
  it('visits every card and returns in both directions', () => {
    let index = 0;
    const seen = new Set<number>();
    for (let i = 0; i < 8; i++) {
      seen.add(index);
      index = stepBoundCard(index, 1, 8);
    }
    expect(seen.size).toBe(8);
    expect(index).toBe(0);
    expect(stepBoundCard(0, -1, 8)).toBe(7);
    expect(cardWindow(7, 8)).toEqual([7, 0, 1]);
  });
});
