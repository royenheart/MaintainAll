import { describe, expect, it } from 'vitest';
import { PerspectiveCamera, Vector3 } from 'three';
import {
  radiationRays,
  radiationPoint,
  radiationState,
  createRadiationGeometry,
  updateRadiationGeometry,
} from '../../src/scenes/radiation';

describe('spatial radiation', () => {
  it('extends coherent strands beyond the short-trace envelope without changing packet travel', () => {
    const point = (ray: number, q: number, along: number, streaming: boolean) =>
      radiationPoint(
        radiationRays[ray]!,
        q,
        along,
        12,
        new Vector3(),
        streaming,
      );
    const height = (streaming: boolean) =>
      point(0, 0.2, 1, streaming).y - point(0, 0.2, 0, streaming).y;
    expect(height(true) / height(false)).toBeGreaterThan(2.7);
    for (let ray = 0; ray < 5; ray++) {
      const before = point(ray, 0.16, 0.5, true);
      const after = point(ray, 0.36, 0.5, true);
      expect(after.z).toBeGreaterThan(before.z);
      expect(after.y).toBeLessThan(before.y);
    }
  });

  it('emits separate packets along a fan of world-space radial trajectories', () => {
    const a = new Vector3(),
      b = new Vector3();
    for (const ray of radiationRays.slice(0, 5)) {
      radiationPoint(ray, 0.16, 0.5, 12, a);
      radiationPoint(ray, 0.36, 0.5, 12, b);
      expect(Math.hypot(b.x, b.z)).toBeGreaterThan(Math.hypot(a.x, a.z));
      expect(b.z).toBeGreaterThan(a.z);
      expect(b.y).toBeLessThan(a.y);
    }
    expect(radiationState(radiationRays[0]!, 0.2).opacity).toBeGreaterThan(0);
    expect(radiationState(radiationRays[5]!, 0.2).opacity).toBe(0);
    for (const ray of radiationRays)
      expect(radiationState(ray, 1).opacity).toBe(0);
  });

  it('projects frontward travel downward and increases apparent height through perspective', () => {
    const camera = new PerspectiveCamera(62, 1.5, 0.1, 200);
    camera.position.set(0, 1.4, 22);
    camera.lookAt(0, 1.4, -38);
    camera.updateMatrixWorld();
    const project = (q: number, along: number) =>
      radiationPoint(radiationRays[2]!, q, along, 12, new Vector3())
        .multiplyScalar(5)
        .add(new Vector3(0, 1.4, -38))
        .project(camera);
    const before = project(0.14, 0.5),
      after = project(0.28, 0.5);
    expect(after.y).toBeLessThan(before.y - 0.1);
    const initialHeight = project(0.14, 1).y - project(0.14, 0).y;
    const laterHeight = project(0.28, 1).y - project(0.28, 0).y;
    expect(laterHeight / initialHeight).toBeGreaterThan(1.2);
  });

  it('reuses finite strip geometry and reproduces the same phase', () => {
    const geometry = createRadiationGeometry();
    const attribute = geometry.getAttribute('position');
    updateRadiationGeometry(geometry, 0.3, 12);
    const first = Float32Array.from(attribute.array);
    updateRadiationGeometry(geometry, 0.6, 12);
    expect(attribute.array).not.toEqual(first);
    updateRadiationGeometry(geometry, 0.3, 12);
    expect(geometry.getAttribute('position')).toBe(attribute);
    expect(attribute.array).toEqual(first);
    expect([...attribute.array].every(Number.isFinite)).toBe(true);
    geometry.dispose();
  });
});
