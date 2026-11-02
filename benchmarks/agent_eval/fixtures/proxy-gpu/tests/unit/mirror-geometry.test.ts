import { describe, expect, it } from 'vitest';
import { createMirrorGeometry } from '../../src/scenes/mirrorGeometry';

describe('mirror surface partition', () => {
  it.each([390 / 844, 1, 1440 / 900, 1280 / 400])(
    'covers the viewport once with finite, consistently wound triangles at aspect %s',
    (aspect) => {
      const geometry = createMirrorGeometry(82371, aspect);
      const points = geometry.getAttribute('position');
      let area = 0;
      for (let i = 0; i < points.count; i += 3) {
        const ax = points.getX(i),
          ay = points.getY(i);
        const bx = points.getX(i + 1),
          by = points.getY(i + 1);
        const cx = points.getX(i + 2),
          cy = points.getY(i + 2);
        const signed = ((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / 2;
        expect(signed).toBeGreaterThanOrEqual(-1e-7);
        area += signed;
        for (const value of [ax, ay, bx, by, cx, cy]) {
          expect(Number.isFinite(value)).toBe(true);
          expect(Math.abs(value)).toBeLessThanOrEqual(1.000001);
        }
      }
      expect(area).toBeCloseTo(4, 5);
      expect(geometry.userData.cellCount).toBe(35);
      geometry.dispose();
    },
  );

  it('replays its partition and preserves panel identities when resized', () => {
    const first = createMirrorGeometry(82371, 1.5);
    const replay = createMirrorGeometry(82371, 1.5);
    const resized = createMirrorGeometry(82371, 0.5);
    const changed = createMirrorGeometry(1920, 1.5);
    expect(first.getAttribute('position').array).toEqual(
      replay.getAttribute('position').array,
    );
    expect(first.getAttribute('position').array).not.toEqual(
      changed.getAttribute('position').array,
    );
    const identities = (geometry: typeof first) =>
      [...new Set(geometry.getAttribute('aSeed').array)].sort();
    expect(identities(first)).toEqual(identities(resized));
    for (const geometry of [first, replay, resized, changed])
      geometry.dispose();
  });
});
