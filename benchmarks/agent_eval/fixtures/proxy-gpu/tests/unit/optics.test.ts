import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { describe, expect, it } from 'vitest';
import manifest from '../../src/scenes/relativity/manifest.json';
import {
  CRITICAL_IMPACT,
  CRITICAL_ENERGY_SQUARED,
  TABLE_SIZES,
  OPTICAL_VERSION,
  advanceRay,
  angleUpperBound,
  decodeTable,
  sampleTable,
  traceOpticalRay,
} from '../../src/scenes/relativity/optics';

const bytes = (file: string) =>
  new Uint8Array(
    readFileSync(new URL(`../../public/optics/${file}`, import.meta.url)),
  );
const deflections = decodeTable(
  bytes('deflection.dat').buffer,
  TABLE_SIZES.deflection,
);
const inverseRadii = decodeTable(
  bytes('inverse-radius.dat').buffer,
  TABLE_SIZES.inverseRadius,
);

// Independent symplectic Euler reference: test integration differs from table generation.
function reference(radius: number, delta: number, alpha: number) {
  const step = 0.00001;
  let u = 1 / radius,
    v = -u / Math.tan(delta),
    phi = 0;
  const intersections: number[] = [];
  let plane = Math.sin(-alpha);
  while (phi < 25) {
    const previousU = u;
    v += (1.5 * u * u - u) * step;
    u += v * step;
    phi += step;
    const nextPlane = Math.sin(phi - alpha);
    if (plane * nextPlane < 0 && u > 0 && u < 1) intersections.push(1 / u);
    plane = nextPlane;
    if (u >= 1) return { deflection: -1, intersections };
    if (u <= 0)
      return {
        deflection: phi - step + (step * previousU) / (previousU - u) - delta,
        intersections,
      };
  }
  throw new Error('Reference ray did not terminate');
}

describe('Schwarzschild optical assets', () => {
  it('matches the version, dimensions, finite samples and recorded checksums', () => {
    expect(manifest.version).toBe(OPTICAL_VERSION);
    for (const asset of Object.values(manifest.files) as {
      file: string;
      sha256: string;
      bytes: number;
    }[]) {
      const data = bytes(asset.file);
      expect(data.byteLength).toBe(asset.bytes);
      expect(createHash('sha256').update(data).digest('hex')).toBe(
        asset.sha256,
      );
    }
    expect(deflections.data.every(Number.isFinite)).toBe(true);
    expect(inverseRadii.data.every(Number.isFinite)).toBe(true);
  });

  it('rejects truncated, incompatible and non-finite tables', () => {
    expect(() =>
      decodeTable(new ArrayBuffer(8), TABLE_SIZES.deflection),
    ).toThrow(/length/);
    const data = bytes('inverse-radius.dat');
    new DataView(data.buffer).setFloat32(0, 2, true);
    expect(() => decodeTable(data.buffer, TABLE_SIZES.inverseRadius)).toThrow(
      /dimensions/,
    );
    new DataView(data.buffer).setFloat32(0, TABLE_SIZES.inverseRadius[0], true);
    new DataView(data.buffer).setFloat32(12, Infinity, true);
    expect(() => decodeTable(data.buffer, TABLE_SIZES.inverseRadius)).toThrow(
      /Non-finite/,
    );
  });

  it('conserves the null-geodesic energy and the photon circular orbit', () => {
    let state = { u: 2 / 3, velocity: 0, phi: 0, time: 0 };
    for (let i = 0; i < 1000; i++)
      state = advanceRay(state, Math.sqrt(CRITICAL_ENERGY_SQUARED), 0.001);
    expect(state.u).toBeCloseTo(2 / 3, 10);
    state = {
      u: 0.01,
      velocity: Math.sqrt(0.09 - 0.01 ** 2 * 0.99),
      phi: 0,
      time: 0,
    };
    for (let i = 0; i < 3000; i++) state = advanceRay(state, 0.3, 0.001);
    expect(state.velocity ** 2 + state.u ** 2 * (1 - state.u)).toBeCloseTo(
      0.09,
      9,
    );
  });

  it('agrees with independent capture/escape, bending and disk intersections', () => {
    for (const impact of [1.7, 2.5, 2.59, 2.7, 3.1, 4, 6, 10, 18]) {
      const radius = 30,
        u = 1 / radius;
      const velocity = Math.sqrt(1 / impact ** 2 - u * u * (1 - u));
      const delta = Math.PI - Math.atan(u / velocity),
        alpha = 1.3;
      const actual = traceOpticalRay(
        deflections,
        inverseRadii,
        radius,
        delta,
        alpha,
      );
      const expected = reference(radius, delta, alpha);
      expect(actual.deflection < 0, `capture at b=${impact}`).toBe(
        impact < CRITICAL_IMPACT,
      );
      expect(
        Math.abs(actual.deflection - expected.deflection),
        `bending at b=${impact}`,
      ).toBeLessThan(0.006);
      const visible = (values: number[]) =>
        values.filter((r) => r > 3.05 && r < 12).sort((a, b) => a - b);
      const measured = visible(actual.intersections),
        predicted = visible(expected.intersections);
      expect(measured.length, `disk count at b=${impact}`).toBe(
        predicted.length,
      );
      measured.forEach((r, i) =>
        expect(
          Math.abs(r - predicted[i]!) / predicted[i]!,
          `disk radius at b=${impact}`,
        ).toBeLessThan(0.015),
      );
    }
  });

  it('approaches weak-field deflection and resolves inverse radius lookup', () => {
    const ray = traceOpticalRay(
      deflections,
      inverseRadii,
      10000,
      Math.PI - Math.asin(80 / 10000),
      1,
    );
    expect(Math.abs(ray.deflection / (2 / 80) - 1)).toBeLessThan(0.06);
    for (const impact of [3, 4, 8, 20]) {
      const energySquared = 1 / impact ** 2;
      const phi = angleUpperBound(energySquared) * 0.7;
      let state = { u: 0, velocity: 1 / impact, phi: 0, time: 0 };
      const step = phi / 5000;
      for (let i = 0; i < 5000; i++)
        state = advanceRay(state, 1 / impact, step);
      const actual = sampleTable(
        inverseRadii,
        1 / (1 + 6 * energySquared),
        0.7,
      )[0];
      expect(Math.abs(actual - state.u)).toBeLessThan(0.0015);
    }
  });
});
