/**
 * Copyright (c) 2020 Eric Bruneton
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright notice, this
 * list of conditions and the following disclaimer.
 *
 * 2. Redistributions in binary form must reproduce the above copyright notice,
 * this list of conditions and the following disclaimer in the documentation
 * and/or other materials provided with the distribution.
 *
 * 3. Neither the name of the copyright holder nor the names of its contributors
 * may be used to endorse or promote products derived from this software without
 * specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
 * FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
 * CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
 * OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

// Coordinate mappings follow Eric Bruneton's BSD-3-Clause black hole model.
// See bruneton-functions.glsl and public/optics/LICENSE for the full notice.
export const CRITICAL_ENERGY_SQUARED = 4 / 27;
export const CRITICAL_IMPACT = Math.sqrt(27) / 2;
export const OPTICAL_VERSION = 'schwarzschild-rk4-v1';
export const TABLE_SIZES = {
  deflection: [512, 512],
  inverseRadius: [128, 64],
} as const;

export const clamp = (x: number, low = 0, high = 1) =>
  Math.min(high, Math.max(low, x));
export function energyFromDeflectionCoordinate(x: number) {
  const y = -Math.expm1(-50 * (x - 0.5) ** 2);
  return x < 0.5 ? CRITICAL_ENERGY_SQUARED * y : CRITICAL_ENERGY_SQUARED / y;
}
export function deflectionCoordinate(energySquared: number) {
  return energySquared < CRITICAL_ENERGY_SQUARED
    ? 0.5 -
        Math.sqrt(-Math.log1p(-energySquared / CRITICAL_ENERGY_SQUARED) / 50)
    : 0.5 +
        Math.sqrt(-Math.log1p(-CRITICAL_ENERGY_SQUARED / energySquared) / 50);
}
export function apsisInverseRadius(energySquared: number) {
  return (
    1 / 3 +
    (2 / 3) *
      Math.sin(
        Math.asin(
          clamp((2 * energySquared) / CRITICAL_ENERGY_SQUARED - 1, -1, 1),
        ) / 3,
      )
  );
}
export function deflectionRadiusCoordinate(energySquared: number, u: number) {
  if (energySquared > CRITICAL_ENERGY_SQUARED) {
    const offset = Math.sign(u - 2 / 3) * Math.sqrt(Math.abs(u - 2 / 3));
    return (Math.sqrt(2 / 3) + offset) / (Math.sqrt(2 / 3) + Math.sqrt(1 / 3));
  }
  return 1 - Math.sqrt(Math.max(1 - u / apsisInverseRadius(energySquared), 0));
}
export const angleUpperBound = (energySquared: number) =>
  (1 + energySquared) / (1 / 3 + 2 * energySquared * Math.sqrt(energySquared));

export interface RayState {
  u: number;
  velocity: number;
  phi: number;
  time: number;
}
// Fourth-order integration of u'' = 1.5 u² - u, in units where r_s = 1.
export function advanceRay(
  state: RayState,
  energy: number,
  step: number,
): RayState {
  const acceleration = (u: number) => 1.5 * u * u - u;
  const { u, velocity: v } = state;
  const k1u = v,
    k1v = acceleration(u);
  const k2u = v + (step * k1v) / 2,
    k2v = acceleration(u + (step * k1u) / 2);
  const k3u = v + (step * k2v) / 2,
    k3v = acceleration(u + (step * k2u) / 2);
  const k4u = v + step * k3v,
    k4v = acceleration(u + step * k3u);
  const nextU = u + (step * (k1u + 2 * k2u + 2 * k3u + k4u)) / 6;
  const midpoint = (u + nextU) / 2;
  // The common time origin at u=0.01 cancels when intersecting a finite ray.
  const elapsed =
    midpoint > 0.01 && midpoint < 0.99999
      ? (energy * step) / (midpoint * midpoint * (1 - midpoint))
      : 0;
  return {
    u: nextU,
    velocity: v + (step * (k1v + 2 * k2v + 2 * k3v + k4v)) / 6,
    phi: state.phi + step,
    time: state.time + elapsed,
  };
}

export interface OpticalTable {
  width: number;
  height: number;
  data: Float32Array;
}
export function sampleTable(
  table: OpticalTable,
  x: number,
  y: number,
): [number, number] {
  const px = clamp(x) * (table.width - 1),
    py = clamp(y) * (table.height - 1);
  const x0 = Math.floor(px),
    y0 = Math.floor(py);
  const x1 = Math.min(x0 + 1, table.width - 1),
    y1 = Math.min(y0 + 1, table.height - 1);
  return [0, 1].map((channel) => {
    const value = (ix: number, iy: number) =>
      table.data[2 * (ix + iy * table.width) + channel]!;
    const top = value(x0, y0) * (1 - px + x0) + value(x1, y0) * (px - x0);
    const bottom = value(x0, y1) * (1 - px + x0) + value(x1, y1) * (px - x0);
    return top * (1 - py + y0) + bottom * (py - y0);
  }) as [number, number];
}

export function decodeTable(
  buffer: ArrayBuffer,
  dimensions: readonly [number, number],
): OpticalTable {
  const [width, height] = dimensions;
  if (buffer.byteLength !== (width * height * 2 + 2) * 4)
    throw new Error('Optical table byte length mismatch');
  const view = new DataView(buffer);
  if (view.getFloat32(0, true) !== width || view.getFloat32(4, true) !== height)
    throw new Error('Optical table dimensions mismatch');
  const data = new Float32Array(width * height * 2);
  for (let i = 0; i < data.length; i++) {
    const value = view.getFloat32((i + 2) * 4, true);
    if (!Number.isFinite(value))
      throw new Error('Non-finite optical table sample');
    data[i] = value;
  }
  return { width, height, data };
}

export function traceOpticalRay(
  deflections: OpticalTable,
  inverseRadii: OpticalTable,
  radius: number,
  delta: number,
  alpha: number,
) {
  const u = 1 / radius,
    velocity = -u / Math.tan(delta);
  const energySquared = velocity * velocity + u * u * (1 - u);
  const escaping = energySquared < CRITICAL_ENERGY_SQUARED;
  const coordinate = deflectionCoordinate(energySquared);
  const apsis = sampleTable(deflections, coordinate, 1)[0];
  const angle = sampleTable(
    deflections,
    coordinate,
    deflectionRadiusCoordinate(energySquared, u),
  )[0];
  const deflection = velocity > 0 ? (escaping ? 2 * apsis - angle : -1) : angle;
  const sign = Math.sign(velocity);
  const phi = angle + (sign === 1 ? Math.PI - delta : delta) + sign * alpha;
  const apsisAngle = apsis + Math.PI / 2;
  const moduloPi = (value: number) => ((value % Math.PI) + Math.PI) % Math.PI;
  const p0 = moduloPi(phi),
    p1 = moduloPi(2 * apsisAngle - phi);
  const lookup = (p: number) =>
    sampleTable(
      inverseRadii,
      1 / (1 + 6 * energySquared),
      p / angleUpperBound(energySquared),
    )[0];
  let u0 = -1,
    u1 = -1;
  const first = lookup(p0);
  if (p0 < apsisAngle) {
    const side = sign * (first - u);
    if (side > 0.001 || (side > -0.001 && alpha < delta)) u0 = first;
  }
  if (escaping && sign === 1 && p1 < apsisAngle) u1 = lookup(p1);
  return {
    deflection,
    intersections: [u0, u1]
      .filter((value) => value > 0)
      .map((value) => 1 / value),
  };
}
