import { CRITICAL_IMPACT } from './optics';

export const HORIZON_CENTER = [0, 1.4, -38] as const;
export const HORIZON_VIEW_HEIGHT = 13;
export type HorizonTreatment = 'optical' | 'limb';

export function horizonViewHeight(
  width: number,
  height: number,
  treatment: HorizonTreatment = 'optical',
) {
  return (
    (treatment === 'limb' ? 7.2 : HORIZON_VIEW_HEIGHT) *
    Math.max(1, height / width)
  );
}

// Convert the apparent capture radius into the cube cloud's world-space plane.
export function horizonCaptureRadius(
  width: number,
  height: number,
  distance: number,
  verticalFov: number,
  treatment: HorizonTreatment = 'optical',
) {
  const frameHeight = 2 * distance * Math.tan((verticalFov * Math.PI) / 360);
  return (
    (frameHeight * CRITICAL_IMPACT) /
    horizonViewHeight(width, height, treatment)
  );
}
