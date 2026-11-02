export type AccretionStyle = 'legacy' | 'split' | 'orbit' | 'cascade';
export type CubeArrivalStyle = 'layered' | 'gravity';

export const accretionModes: Record<AccretionStyle, number> = {
  legacy: 0,
  split: 1,
  orbit: 2,
  cascade: 3,
};
