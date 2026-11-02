export const cardFinishes = ['original', 'inset', 'nameplate', 'seam'] as const;
export type CardFinish = (typeof cardFinishes)[number];

export function parseCardFinish(value: string | null): CardFinish {
  return cardFinishes.find((finish) => finish === value) ?? 'nameplate';
}

export const surfaceMotions = ['still', 'drift', 'layers', 'light'] as const;
export type SurfaceMotion = (typeof surfaceMotions)[number];
export function parseSurfaceMotion(value: string | null): SurfaceMotion {
  return surfaceMotions.find((motion) => motion === value) ?? 'drift';
}

export const elsewhereStudies = ['glyph', 'index', 'tile'] as const;
export type ElsewhereStudy = (typeof elsewhereStudies)[number];
export function parseElsewhereStudy(value: string | null): ElsewhereStudy {
  return elsewhereStudies.find((study) => study === value) ?? 'tile';
}

export const cardExtractions = ['slide', 'lift', 'fan'] as const;
export type CardExtraction = (typeof cardExtractions)[number];
export function parseCardExtraction(value: string | null): CardExtraction {
  return cardExtractions.find((motion) => motion === value) ?? 'slide';
}

export const cardMaterials = ['drift', 'light', 'layers'] as const;
export type CardMaterial = (typeof cardMaterials)[number];
export function parseCardMaterial(value: string | null): CardMaterial {
  return cardMaterials.find((material) => material === value) ?? 'drift';
}

export const cardArtStudies = ['engraving', 'foil', 'relief'] as const;
export type CardArtStudy = (typeof cardArtStudies)[number];
export type CardArtSelection = CardArtStudy | 'scene';
export function parseCardArtStudy(value: string | null): CardArtSelection {
  return cardArtStudies.find((art) => art === value) ?? 'scene';
}

export const elsewhereMarks = ['emblem', 'intaglio', 'editorial'] as const;
export type ElsewhereMark = (typeof elsewhereMarks)[number];
export function parseElsewhereMark(value: string | null): ElsewhereMark {
  return elsewhereMarks.find((mark) => mark === value) ?? 'editorial';
}
