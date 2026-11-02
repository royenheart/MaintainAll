import { MathUtils } from 'three';

// Keep the source connected until the corruption has crossed the composition.
export const GLITCH_FRACTURE_START = 0.64;
export function glitchFractureProgress(progress: number): number {
  return MathUtils.clamp(
    (progress - GLITCH_FRACTURE_START) / (1 - GLITCH_FRACTURE_START),
    0,
    1,
  );
}
export type GlitchDiagnostic = 'beauty' | 'field' | 'sharp';
