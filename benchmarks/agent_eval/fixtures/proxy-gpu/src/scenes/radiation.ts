import { BufferGeometry, Float32BufferAttribute, Vector3 } from 'three';

export interface RadiationRay {
  angle: number;
  launch: number;
  height: number;
  phase: number;
}
export const radiationRays: readonly RadiationRay[] = Array.from(
  { length: 15 },
  (_, index) => {
    const sector = index % 5;
    const packet = Math.floor(index / 5);
    const phase = index * 2.399963;
    return {
      angle: (sector - 2) * 0.64 + Math.sin(phase) * 0.045,
      launch: 0.08 + packet * 0.19 + (sector % 2) * 0.013,
      height: 4.4 + Math.sin(phase * 1.7) * 0.65,
      phase,
    };
  },
);

export function radiationState(ray: RadiationRay, progress: number) {
  const age = (progress - ray.launch) / 0.62;
  const smooth = (start: number, end: number, value: number) => {
    const t = Math.min(1, Math.max(0, (value - start) / (end - start)));
    return t * t * (3 - 2 * t);
  };
  return {
    radius: 5.5 + Math.max(age, 0) * 7.4,
    opacity:
      smooth(0, 0.09, age) *
      (1 - smooth(0.78, 1, age)) *
      (1 - smooth(0.88, 1, progress)),
  };
}

// Curves stand above a tilted disk. Their anchors travel in the disk plane,
// including depth toward the observer, rather than along a screen-space axis.
export function radiationPoint(
  ray: RadiationRay,
  progress: number,
  along: number,
  time: number,
  out: Vector3,
  streaming = false,
) {
  const { radius } = radiationState(ray, progress);
  const y = (along - 0.5) * ray.height * (streaming ? 2.85 : 1);
  // Neighboring strands share the broad disturbance, with smaller local detail.
  const broad =
    Math.sin(y * 0.43 - time * 0.14) * 0.32 +
    Math.sin(y * 0.91 + time * 0.09) * 0.1;
  const bend = streaming
    ? broad +
      Math.sin(y * 2.7 + ray.phase) * 0.035 +
      Math.sin(y * 7.1 - ray.phase * 0.7) * 0.012
    : Math.sin(y * 1.45 + ray.phase + time * 0.13) * 0.12 +
      Math.sin(y * 3.3 - ray.phase * 1.3 - time * 0.09) * 0.035 +
      Math.sin(y * 11.7 + ray.phase * 4) * 0.007;
  const envelope = streaming ? Math.sin(y * 0.37 - time * 0.1) * 0.24 : 0;
  const x =
    Math.sin(ray.angle) * (radius + envelope) + Math.cos(ray.angle) * bend;
  const z =
    Math.cos(ray.angle) * (radius + envelope) - Math.sin(ray.angle) * bend;
  return out.set(
    x,
    y - Math.sin(Math.PI / 15) * z - 0.15,
    Math.cos(Math.PI / 15) * z,
  );
}

const segments = 96;
export function createRadiationGeometry() {
  const count = radiationRays.length * (segments + 1) * 2;
  const geometry = new BufferGeometry();
  for (const name of ['position', 'aTangent'])
    geometry.setAttribute(
      name,
      new Float32BufferAttribute(new Float32Array(count * 3), 3),
    );
  for (const name of ['aSide', 'aAlong', 'aLife'])
    geometry.setAttribute(
      name,
      new Float32BufferAttribute(new Float32Array(count), 1),
    );
  const indices: number[] = [];
  radiationRays.forEach((_, index) => {
    const start = index * (segments + 1) * 2;
    for (let segment = 0; segment < segments; segment++) {
      const a = start + segment * 2;
      indices.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
    }
  });
  geometry.setIndex(indices);
  return geometry;
}

const samples = Array.from({ length: segments + 1 }, () => new Vector3());
const tangent = new Vector3();
export function updateRadiationGeometry(
  geometry: BufferGeometry,
  progress: number,
  time: number,
  streaming = false,
) {
  const positions = geometry.getAttribute('position');
  const tangents = geometry.getAttribute('aTangent');
  const sides = geometry.getAttribute('aSide');
  const alongs = geometry.getAttribute('aAlong');
  const lives = geometry.getAttribute('aLife');
  radiationRays.forEach((ray, index) => {
    const { opacity } = radiationState(ray, progress);
    for (let j = 0; j <= segments; j++)
      radiationPoint(ray, progress, j / segments, time, samples[j]!, streaming);
    for (let j = 0; j <= segments; j++) {
      tangent
        .subVectors(
          samples[Math.min(segments, j + 1)]!,
          samples[Math.max(0, j - 1)]!,
        )
        .normalize();
      for (let side = 0; side < 2; side++) {
        const vertex = (index * (segments + 1) + j) * 2 + side;
        const point = samples[j]!;
        positions.setXYZ(vertex, point.x, point.y, point.z);
        tangents.setXYZ(vertex, tangent.x, tangent.y, tangent.z);
        sides.setX(vertex, side * 2 - 1);
        alongs.setX(vertex, j / segments);
        lives.setX(vertex, opacity);
      }
    }
  });
  for (const attribute of [positions, tangents, sides, alongs, lives])
    attribute.needsUpdate = true;
}
