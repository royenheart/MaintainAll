import { describe, expect, it } from 'vitest';
import {
  ORBIT_PIXEL_BUDGET,
  orbitPixelRatio,
} from '../../src/scenes/render-budget';

describe('Orbit fragment budget', () => {
  it.each([
    [390, 844, 3],
    [1440, 900, 2],
    [1920, 1080, 1],
    [3840, 2160, 2],
    [7680, 4320, 2],
  ])(
    'bounds actual pixels at %i×%i with device DPR %i',
    (width, height, dpr) => {
      const ratio = orbitPixelRatio(width, height, dpr, 1);
      expect(width * height * ratio ** 2).toBeLessThanOrEqual(
        ORBIT_PIXEL_BUDGET + 1,
      );
      expect(ratio).toBeLessThanOrEqual(dpr);
    },
  );
  it('reduces fragment work under pressure without changing the CSS layout', () => {
    const high = orbitPixelRatio(1920, 1080, 2, 1);
    const low = orbitPixelRatio(1920, 1080, 2, 0.45);
    expect(low ** 2 / high ** 2).toBeLessThan(0.21);
    expect(orbitPixelRatio(0, 0, 1, 1)).toBe(1);
  });
});
