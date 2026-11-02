import { expect, it } from 'vitest';
import {
  adjacentScene,
  cardIndex,
  randomScene,
  sceneBlend,
} from '../../src/explorations/orbit/sequence';

it('wraps the ordered cycle and reverses each adjacent edge', () => {
  for (const start of ['cubes', 'horizon'] as const) {
    expect(adjacentScene(adjacentScene(start, 1), -1)).toBe(start);
    expect(adjacentScene(start, 1)).not.toBe(start);
    expect(sceneBlend(start) + sceneBlend(adjacentScene(start, 1))).toBe(1);
  }
});
it('keeps the final navigation card reachable instead of wrapping past it', () => {
  expect(cardIndex(3, 1, 4)).toBe(3);
  expect(cardIndex(0, -1, 4)).toBe(0);
  expect(cardIndex(1, 240, 4)).toBe(2);
  expect(() => cardIndex(0, 1, 0)).toThrow();
});
it('chooses a bounded initial scene without randomizing subsequent transitions', () => {
  expect(randomScene(0)).toBe('cubes');
  expect(randomScene(0.99)).toBe('horizon');
  expect(randomScene(1)).toBe('horizon');
});
