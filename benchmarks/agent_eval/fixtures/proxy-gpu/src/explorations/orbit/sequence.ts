import type { SceneId } from '../../lib/content/schema';

export const sceneOrder: readonly SceneId[] = ['cubes', 'horizon'];
export type MotionStudy = 'gather' | 'vortex' | 'collapse';
export const motionStudies = {
  collapse: {
    id: 'F3',
    label: 'Collapse and rupture',
    swirl: 0,
    duration: 6.4,
  },
  gather: { id: 'S1', label: 'Gather', swirl: 0, duration: 6 },
  vortex: { id: 'S2', label: 'Vortex', swirl: 1.8, duration: 6 },
} as const;

export function adjacentScene(scene: SceneId, direction: 1 | -1): SceneId {
  const index = sceneOrder.indexOf(scene);
  if (index < 0) throw new Error('Unknown scene');
  return sceneOrder[
    (index + direction + sceneOrder.length) % sceneOrder.length
  ]!;
}

export function sceneBlend(scene: SceneId) {
  return scene === 'cubes' ? 0 : 1;
}
export function cardIndex(index: number, direction: number, count: number) {
  if (!Number.isInteger(count) || count < 1)
    throw new Error('A deck must contain cards');
  return Math.min(count - 1, Math.max(0, index + Math.sign(direction)));
}

export function randomScene(random = Math.random()): SceneId {
  return sceneOrder[
    Math.min(
      sceneOrder.length - 1,
      Math.max(0, Math.floor(random * sceneOrder.length)),
    )
  ]!;
}
