export const presentationStudies = {
  a: { font: 'manrope', cover: 'ripple', identity: 'orbit' },
  b: { font: 'plex', cover: 'frost', identity: 'badge' },
  c: { font: 'fraunces', cover: 'meniscus', identity: 'route' },
} as const;

export type FontStudy = 'manrope' | 'plex' | 'fraunces';
export type CoverStudy = 'ripple' | 'frost' | 'meniscus';
export type CoverSelection = CoverStudy | 'random';
export type DetailStudy = 'none' | 'etch' | 'flow' | 'orbit';
export type IdentityStudy = 'orbit' | 'badge' | 'route';

export function randomCoverStudy(): CoverStudy {
  const effects: readonly CoverStudy[] = ['ripple', 'frost', 'meniscus'];
  return effects[Math.floor(Math.random() * effects.length)]!;
}

export function smoothRange(value: number, start: number, end: number) {
  const t = Math.max(0, Math.min(1, (value - start) / (end - start)));
  return t * t * (3 - 2 * t);
}
