export const rotaryDesigns = {
  tangent: {
    title: 'A / Tangent glass',
    mechanism: 'Top-aligned radial carousel',
    description:
      'A softened taper, etched facets and a shallow sweep around the artwork center.',
    step: 16,
  },
  drum: {
    title: 'B / Velvet drum',
    mechanism: 'Vertical cylindrical carousel',
    description:
      'A round capsule rolls over a cylinder, with neighboring cards receding in depth.',
    step: 55,
  },
  orbit: {
    title: 'C / Orbital ribbon',
    mechanism: 'Banked orbital carousel',
    description:
      'A slender curved ribbon follows an elliptical path and banks toward the artwork.',
    step: 52,
  },
} as const;

export type RotaryDesign = keyof typeof rotaryDesigns;
export type DockDesign = 'classic' | RotaryDesign;
