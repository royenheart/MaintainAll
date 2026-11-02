export const ORBIT_PIXEL_BUDGET = 1_300_000;

/** Bound fragment work independently of display resolution and device DPR. */
export function orbitPixelRatio(
  width: number,
  height: number,
  deviceRatio: number,
  quality: number,
) {
  const pixels = Math.max(1, width) * Math.max(1, height);
  return (
    Math.min(
      Math.max(0.1, deviceRatio),
      1.2,
      Math.sqrt(ORBIT_PIXEL_BUDGET / pixels),
    ) * Math.max(0.45, Math.min(1, quality))
  );
}
